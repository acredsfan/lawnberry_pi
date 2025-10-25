import { ref, onUnmounted } from 'vue'

export interface WebSocketMessage {
  event: string
  topic?: string
  timestamp: string
  data?: any
  client_id?: string
}

export class WebSocketService {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private subscriptions = new Set<string>()
  private listeners = new Map<string, Array<(data: any) => void>>()

  private urlCandidates: string[]
  private urlIndex = 0

  constructor(private url: string) {
    // Build fallback candidates: primary /api/v2/ws/telemetry, then /ws
    try {
      const u = new URL(url)
      const alt = `${u.protocol}//${u.host}/ws`
      this.urlCandidates = [url]
      if (alt !== url) this.urlCandidates.push(alt)
    } catch {
      // Fallback if URL parsing fails
      this.urlCandidates = [url]
    }
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const tryConnect = () => {
        const target = this.urlCandidates[this.urlIndex] || this.urlCandidates[0]
        try {
          this.ws = new WebSocket(target)
        
          this.ws.onopen = () => {
            console.log('WebSocket connected:', target)
            this.reconnectAttempts = 0
            // Remember working endpoint and stick to it across reconnects
            const goodIndex = this.urlCandidates.indexOf(target)
            if (goodIndex >= 0) this.urlIndex = goodIndex
          
          // Re-subscribe to topics after reconnection
          this.subscriptions.forEach(topic => {
            this.subscribe(topic)
          })
            // Optional: set default cadence
            this.setCadence(5)
          
          resolve()
          }
        
          this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            this.handleMessage(message)
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
          }
        
          this.ws.onclose = () => {
            console.log('WebSocket disconnected')
            this.handleReconnect()
          }
        
          this.ws.onerror = (error) => {
            console.error('WebSocket error:', error)
            // Try alternate candidate once before giving up initial connect
            if (this.urlCandidates.length > 1 && this.urlIndex < this.urlCandidates.length - 1) {
              this.urlIndex++
              tryConnect()
            } else {
              // Allow reconnect loop to proceed
              this.handleReconnect()
              // Resolve after scheduling reconnect to avoid unhandled rejections in callers
              resolve()
            }
          }
        } catch (error) {
          // Try alternate or schedule reconnect
          if (this.urlCandidates.length > 1 && this.urlIndex < this.urlCandidates.length - 1) {
            this.urlIndex++
            tryConnect()
          } else {
            this.handleReconnect()
            resolve()
          }
        }
      }

      tryConnect()
    })
  }

  private handleMessage(message: WebSocketMessage) {
    // Handle different message types
    switch (message.event) {
      case 'telemetry.data':
        if (message.topic) {
          this.emitToListeners(message.topic, message.data)
        }
        break
      case 'connection.established':
        console.log('Connection established:', message.client_id)
        break
      case 'subscription.confirmed':
        console.log('Subscription confirmed for topic:', message.topic)
        break
      case 'subscription.error':
        console.error('Subscription error:', message)
        break
      case 'pong':
        console.log('Received pong')
        break
      default:
        console.log('Unhandled message:', message)
    }
  }

  private emitToListeners(topic: string, data: any) {
    const topicListeners = this.listeners.get(topic)
    if (topicListeners) {
      topicListeners.forEach((callback) => {
        try {
          callback(data)
        } catch (err) {
          console.error(`WebSocket listener for topic "${topic}" failed:`, err)
        }
      })
    }
  }

  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      const backoff = this.reconnectDelay * this.reconnectAttempts
      const jitter = Math.floor(Math.random() * 250)
      console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${backoff + jitter}ms`)

      // Only rotate if previous attempt failed immediately (onerror). If connection existed, keep same index.

      setTimeout(() => {
        this.connect().catch(() => {/* handled inside connect */})
      }, backoff + jitter)
    } else {
      console.error('Max reconnection attempts reached')
    }
  }

  subscribe(topic: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        topic: topic
      }))
      this.subscriptions.add(topic)
    }
  }

  unsubscribe(topic: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'unsubscribe',
        topic: topic
      }))
      this.subscriptions.delete(topic)
    }
  }

  onTopic(topic: string, callback: (data: any) => void) {
    if (!this.listeners.has(topic)) {
      this.listeners.set(topic, [])
    }
    this.listeners.get(topic)!.push(callback)

    // Track desired subscription regardless of current socket state so we can
    // resubscribe on reconnect or initial open.
    const firstTime = !this.subscriptions.has(topic)
    this.subscriptions.add(topic)
    // If connected now, send subscribe frame immediately.
    if (firstTime && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.subscribe(topic)
    }
  }

  offTopic(topic: string, callback?: (data: any) => void) {
    if (callback) {
      const topicListeners = this.listeners.get(topic)
      if (topicListeners) {
        const index = topicListeners.indexOf(callback)
        if (index > -1) {
          topicListeners.splice(index, 1)
        }
        if (topicListeners.length === 0) {
          this.listeners.delete(topic)
          this.unsubscribe(topic)
        }
      }
    } else {
      // Remove all listeners for topic
      this.listeners.delete(topic)
      this.unsubscribe(topic)
    }
  }

  setCadence(cadenceHz: number) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'set_cadence',
        cadence_hz: cadenceHz
      }))
    }
  }

  ping() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'ping'
      }))
    }
  }

  listTopics() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'list_topics'
      }))
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.subscriptions.clear()
    this.listeners.clear()
    this.reconnectAttempts = 0
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  dispatchTestMessage(message: WebSocketMessage) {
    this.handleMessage(message)
  }
}

// Global WebSocket service instance
let wsService: WebSocketService | null = null


// Factory for telemetry or control WebSocket
export function useWebSocket(type: 'telemetry' | 'control' = 'telemetry', handlers?: { onMessage?: (msg: any) => void }) {
  let wsUrl: string
  // If behind a reverse proxy, honor X-Forwarded-Proto via location.protocol
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  if (type === 'telemetry') {
    wsUrl = `${protocol}//${host}/api/v2/ws/telemetry`
  } else {
    wsUrl = `${protocol}//${host}/api/v2/ws/control`
  }
  const wsService = new WebSocketService(wsUrl)

  const connected = ref(false)
  const connecting = ref(false)

  const connect = async () => {
    if (!wsService.isConnected && !connecting.value) {
      connecting.value = true
      try {
        await wsService.connect()
        connected.value = true
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error)
        connected.value = false
      } finally {
        connecting.value = false
      }
    }
  }

  const disconnect = () => {
    wsService.disconnect()
    connected.value = false
  }

  const subscribe = (topic: string, callback: (data: any) => void) => {
    wsService.onTopic(topic, callback)
  }

  const unsubscribe = (topic: string, callback?: (data: any) => void) => {
    wsService.offTopic(topic, callback)
  }

  // Listen for all messages if handler provided
  if (handlers?.onMessage) {
    // Patch handleMessage to call onMessage
    const origHandleMessage = (wsService as any).handleMessage?.bind(wsService)
    ;(wsService as any).handleMessage = function(message: any) {
      handlers.onMessage!(message)
      if (origHandleMessage) origHandleMessage(message)
    }
  }

  onUnmounted(() => {
    // No disconnect here; service may be shared
  })

  return {
    connected,
    connecting,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    setCadence: (hz: number) => wsService.setCadence(hz),
    ping: () => wsService.ping(),
    listTopics: () => wsService.listTopics(),
    dispatchTestMessage: (message: WebSocketMessage) => wsService.dispatchTestMessage(message)
  }
}
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
  private maxReconnectAttempts = -1
  private reconnectDelay = 1000
  private subscriptions = new Set<string>()
  private listeners = new Map<string, Array<(data: any) => void>>()
  private connectionListeners = new Set<(connected: boolean) => void>()
  private rawMessageListeners = new Set<(msg: WebSocketMessage) => void>()
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private lastPongAt = 0
  private _intentionalClose = false
  private _connectionPromise: Promise<void> | null = null

  private urlCandidates: string[]
  private urlIndex = 0

  constructor(private url: string) {
    // Build fallback candidates:
    // - primary (e.g., /api/v2/ws/telemetry)
    // - legacy without /api/v2 prefix but preserving channel (e.g., /ws/telemetry)
    try {
      const u = new URL(url)
      const path = u.pathname
      let altPath = path
      // Replace only the "/api/v2/ws/" prefix while preserving trailing channel
      if (path.startsWith('/api/v2/ws/')) {
        altPath = path.replace(/^\/api\/v2\/ws\//, '/ws/')
      } else if (path === '/api/v2/ws') {
        altPath = '/ws'
      }
      const primary = `${u.protocol}//${u.host}${path}`
      const alt = `${u.protocol}//${u.host}${altPath}`
      this.urlCandidates = [primary]
      if (alt !== primary) this.urlCandidates.push(alt)
    } catch {
      // Fallback if URL parsing fails
      this.urlCandidates = [url]
    }
  }

  connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.notifyConnectionState(true)
      return Promise.resolve()
    }
    // Deduplicate: if a connect attempt is already in flight, return the same promise
    if (this._connectionPromise) {
      return this._connectionPromise
    }
    this._intentionalClose = false

    this._connectionPromise = new Promise((resolve, reject) => {
      let settled = false

      const resolveOnce = () => {
        if (settled) return
        settled = true
        this._connectionPromise = null
        resolve()
      }

      const rejectOnce = (error: Error) => {
        if (settled) return
        settled = true
        this._connectionPromise = null
        reject(error)
      }

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

            // Start heartbeat to keep proxies/tunnels alive (Cloudflare, etc.)
            this.startHeartbeat()
            this.notifyConnectionState(true)
          
          resolveOnce()
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
            this.stopHeartbeat()
            this.notifyConnectionState(false)
            if (!settled) {
              rejectOnce(new Error('WebSocket connection closed before opening'))
              return
            }
            this.handleReconnect()
          }
        
          this.ws.onerror = (error) => {
            // Reduce console noise by rate-limiting error logs
            try {
              (window as any).__ws_last_err ||= 0
              const now = Date.now()
              if (now - (window as any).__ws_last_err > 15000) {
                console.error('WebSocket error:', error)
                ;(window as any).__ws_last_err = now
              }
            } catch {
              // Fallback if window guard fails
              console.error('WebSocket error:', error)
            }
            this.stopHeartbeat()
            this.notifyConnectionState(false)
            // Try alternate candidate once before giving up initial connect
            if (this.urlCandidates.length > 1 && this.urlIndex < this.urlCandidates.length - 1) {
              const failedSocket = this.ws
              if (failedSocket) {
                failedSocket.onopen = null
                failedSocket.onmessage = null
                failedSocket.onclose = null
                failedSocket.onerror = null
                try {
                  failedSocket.close()
                } catch {
                  // ignore close failures while probing alternates
                }
              }
              this.urlIndex++
              tryConnect()
            } else {
              // Allow reconnect loop to proceed
              this.handleReconnect()
              rejectOnce(new Error('WebSocket connection failed'))
            }
          }
        } catch (error) {
          // Try alternate or schedule reconnect
          if (this.urlCandidates.length > 1 && this.urlIndex < this.urlCandidates.length - 1) {
            this.urlIndex++
            tryConnect()
          } else {
            this.handleReconnect()
            this.notifyConnectionState(false)
            rejectOnce(error instanceof Error ? error : new Error('WebSocket connection failed'))
          }
        }
      }

      tryConnect()
    })
    return this._connectionPromise
  }

  private handleMessage(message: WebSocketMessage) {
    // Dispatch to raw (any-message) listeners first
    this.rawMessageListeners.forEach(cb => {
      try { cb(message) } catch { /* ignore listener errors */ }
    })
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
        this.lastPongAt = Date.now()
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
    if (this._intentionalClose) return
    if (this.maxReconnectAttempts >= 0 && this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('Max reconnection attempts reached — switching to fallback polling only')
      return
    }
    if (this.maxReconnectAttempts < 0 || this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      const backoff = Math.min(this.reconnectDelay * this.reconnectAttempts, 30000)
      const jitter = Math.floor(Math.random() * 250)
      // Throttle reconnection log chatter
      try {
        (window as any).__ws_last_reconnect_log ||= 0
        const now = Date.now()
        if (now - (window as any).__ws_last_reconnect_log > 10000) {
          console.log(`Attempting to reconnect... (#${this.reconnectAttempts}) in ${backoff + jitter}ms`)
          ;(window as any).__ws_last_reconnect_log = now
        }
      } catch {
        // best-effort
      }

      // Only rotate if previous attempt failed immediately (onerror). If connection existed, keep same index.

      setTimeout(() => {
        this.connect().catch(() => {/* handled inside connect */})
      }, backoff + jitter)
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
    // Always remove from desired-subscription set so we don't re-subscribe on reconnect
    this.subscriptions.delete(topic)
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'unsubscribe',
        topic: topic
      }))
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
    this._intentionalClose = true
    this._connectionPromise = null
    if (this.ws) {
      // Null handlers before close to prevent onclose from triggering handleReconnect
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onclose = null
      this.ws.onerror = null
      this.ws.close()
      this.ws = null
    }
    this.stopHeartbeat()
    this.notifyConnectionState(false)
    this.subscriptions.clear()
    this.listeners.clear()
    this.reconnectAttempts = 0
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  private startHeartbeat() {
    this.lastPongAt = Date.now()
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    // Send an application-level ping every 25s
    this.heartbeatTimer = setInterval(() => {
      try {
        this.ping()
        // If we haven't seen a pong in 60s, force a reconnect
        if (Date.now() - this.lastPongAt > 60_000) {
          console.warn('WebSocket heartbeat stale; forcing reconnect')
          this.ws?.close()
        }
      } catch {
        /* ignore */
      }
    }, 25_000)
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private notifyConnectionState(connected: boolean) {
    this.connectionListeners.forEach((listener) => {
      try {
        listener(connected)
      } catch (error) {
        console.error('WebSocket connection listener failed:', error)
      }
    })
  }

  onConnectionStateChange(callback: (connected: boolean) => void) {
    this.connectionListeners.add(callback)
    callback(this.isConnected)
    return () => {
      this.connectionListeners.delete(callback)
    }
  }

  onAnyMessage(callback: (msg: WebSocketMessage) => void): () => void {
    this.rawMessageListeners.add(callback)
    return () => { this.rawMessageListeners.delete(callback) }
  }

  dispatchTestMessage(message: WebSocketMessage) {
    this.handleMessage(message)
  }
}

// Per-type singletons — one shared connection per channel (telemetry / control)
const _wsServiceMap: Partial<Record<'telemetry' | 'control', WebSocketService>> = {}

function _buildWsUrl(type: 'telemetry' | 'control'): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  let wsUrl = type === 'telemetry'
    ? `${protocol}//${host}/api/v2/ws/telemetry`
    : `${protocol}//${host}/api/v2/ws/control`
  try {
    const token = localStorage.getItem('auth_token')
    if (token) {
      const url = new URL(wsUrl)
      url.searchParams.set('access_token', token)
      wsUrl = url.toString()
    }
  } catch {
    // ignore
  }
  return wsUrl
}

// Factory for telemetry or control WebSocket — returns a shared singleton per type.
export function useWebSocket(type: 'telemetry' | 'control' = 'telemetry', handlers?: { onMessage?: (msg: any) => void }) {
  // Create singleton on first call for this channel type
  if (!_wsServiceMap[type]) {
    _wsServiceMap[type] = new WebSocketService(_buildWsUrl(type))
  }
  const service = _wsServiceMap[type]!

  const connected = ref(service.isConnected)
  const connecting = ref(false)

  const unsubscribeState = service.onConnectionStateChange((state) => {
    connected.value = state
    if (!state) {
      connecting.value = false
    }
  })

  // Use proper onAnyMessage API instead of monkey-patching handleMessage
  let unsubscribeRaw: (() => void) | null = null
  if (handlers?.onMessage) {
    unsubscribeRaw = service.onAnyMessage(handlers.onMessage)
  }

  const connect = async () => {
    if (!service.isConnected && !connecting.value) {
      connecting.value = true
      try {
        await service.connect()
        connected.value = service.isConnected
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error)
        connected.value = false
      } finally {
        connecting.value = false
      }
    }
  }

  // Disconnect tears down the shared connection and invalidates the singleton
  // so the next connect() call rebuilds with a fresh auth token.
  const disconnect = () => {
    service.disconnect()
    delete _wsServiceMap[type]
    connected.value = false
  }

  onUnmounted(() => {
    unsubscribeState()
    unsubscribeRaw?.()
  })

  return {
    connected,
    connecting,
    connect,
    disconnect,
    subscribe: (topic: string, callback: (data: any) => void) => service.onTopic(topic, callback),
    unsubscribe: (topic: string, callback?: (data: any) => void) => service.offTopic(topic, callback),
    setCadence: (hz: number) => service.setCadence(hz),
    ping: () => service.ping(),
    listTopics: () => service.listTopics(),
    dispatchTestMessage: (message: WebSocketMessage) => service.dispatchTestMessage(message)
  }
}
import { WebSocketMessage } from '../types'
import { store } from '../store/store'
import { setConnectionState } from '../store/slices/mowerSlice'
import { perfMetrics } from '../utils/perfMetrics'

class WebSocketService {
  private socket: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private eventHandlers: Map<string, Function[]> = new Map()
  public connectionState: 'connected' | 'disconnected' | 'connecting' | 'error' = 'disconnected'
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  connect(): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      return
    }

    this.connectionState = 'connecting'
  // perf: mark websocket connect start (only first time)
  perfMetrics.setWebSocketConnectStart()
    
    // Use relative WebSocket URL that works with nginx proxy
    const wsUrl = import.meta.env.DEV 
      ? 'ws://localhost:8000/ws/realtime'
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/realtime`

    console.log('🔌 Connecting to WebSocket:', wsUrl)

    try {
      this.socket = new WebSocket(wsUrl)
      
      // Set a connection timeout
      const connectionTimeout = setTimeout(() => {
        if (this.socket?.readyState === WebSocket.CONNECTING) {
          console.warn('⏰ WebSocket connection timeout')
          this.socket.close()
          this.connectionState = 'error'
          store.dispatch(setConnectionState(false))
          this.emit('error', new Error('Connection timeout'))
        }
      }, 10000) // 10 second timeout
      
      this.socket.onopen = () => {
        clearTimeout(connectionTimeout)
        console.log('✅ WebSocket connected successfully')
        this.connectionState = 'connected'
        this.reconnectAttempts = 0
        store.dispatch(setConnectionState(true))
        this.emit('connect')
  // perf: mark connected
  perfMetrics.setWebSocketConnected()
        
        // Subscribe to all relevant topics after connection
        this.subscribeToTopics()
      }

      this.socket.onclose = (event) => {
        clearTimeout(connectionTimeout)
        console.log('🔌 WebSocket disconnected:', event.reason || 'Unknown reason')
        this.connectionState = 'disconnected'
        store.dispatch(setConnectionState(false))
        this.emit('disconnect', event.reason)
        
        // Only try to reconnect if this wasn't a manual close
        if (event.code !== 1000) {
          this.scheduleReconnect()
        }
      }

      this.socket.onerror = (error) => {
        clearTimeout(connectionTimeout)
        console.error('❌ WebSocket connection error:', error)
        this.connectionState = 'error'
        store.dispatch(setConnectionState(false))
        this.emit('error', error)
      }

      this.socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('❌ Error parsing WebSocket message:', error, 'Raw data:', event.data)
        }
      }
    } catch (error) {
      console.error('❌ Failed to create WebSocket connection:', error)
      this.connectionState = 'error'
      store.dispatch(setConnectionState(false))
      this.emit('error', error)
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    
    if (this.socket) {
      this.socket.close()
      this.socket = null
    }
    
    this.connectionState = 'disconnected'
    store.dispatch(setConnectionState(false))
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnection attempts reached')
      return
    }

    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts), 30000)
    console.log(`Scheduling reconnect in ${delay}ms (attempt ${this.reconnectAttempts + 1})`)
    
    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++
      this.connect()
    }, delay)
  }

  private subscribeToTopics(): void {
    const topics = [
      'system/status',
      'sensors/+/data',
      'navigation/position',
      'navigation/status',
      // Subscribe to canonical power topic and keep legacy alias for compatibility
      'sensors/power/data',
      'power/battery',
      'weather/current',
  'safety/status',
  'safety/alerts/+',
  // RC control status updates (added for RCControl real-time view)
  'rc/status'
    ]

    topics.forEach(topic => {
      this.send({
        type: 'subscribe',
        topic: topic
      })
    })
  }

  send(message: any): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket not connected, cannot send message:', message)
    }
  }

  sendCommand(command: string, parameters?: any): Promise<any> {
    return new Promise((resolve, reject) => {
      if (this.socket?.readyState !== WebSocket.OPEN) {
        reject(new Error('WebSocket not connected'))
        return
      }

      const requestId = Date.now().toString()
      const message = {
        type: 'command',
        command,
        parameters,
        request_id: requestId
      }

      // Set up one-time listener for response
      const timeout = setTimeout(() => {
        this.off('command_response', responseHandler)
        reject(new Error('Command timeout'))
      }, 10000) // 10 second timeout

      const responseHandler = (response: any) => {
        if (response.request_id === requestId) {
          clearTimeout(timeout)
          this.off('command_response', responseHandler)
          
          if (response.success) {
            resolve(response.result)
          } else {
            reject(new Error(response.error || 'Command failed'))
          }
        }
      }

      this.on('command_response', responseHandler)
      this.send(message)
    })
  }

  on(event: string, callback: Function): void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, [])
    }
    this.eventHandlers.get(event)!.push(callback)
  }

  off(event: string, callback: Function): void {
    const handlers = this.eventHandlers.get(event)
    if (handlers) {
      const index = handlers.indexOf(callback)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }

  private emit(event: string, ...args: any[]): void {
    const handlers = this.eventHandlers.get(event)
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(...args)
        } catch (error) {
          console.error(`Error in WebSocket event handler for ${event}:`, error)
        }
      })
    }
  }

  private handleMessage(message: any): void {
    // Handle different message types
    switch (message.type) {
      case 'connection':
        console.log('Received welcome message:', message.message)
        break
        
      case 'mqtt_data':
      case 'data':
      case 'sensor_data':
        // Forward MQTT data to appropriate handlers
        this.emit('data', message.data, message.topic)
        if (message.topic) {
          this.emit(message.topic, message.data)
        }
        // Normalize RC status topic to a simpler event name for UI components
        if (message.topic === 'rc/status') {
          this.emit('rc_status', message.data)
        }
        break
        
      case 'status':
        this.emit('status', message.data)
        break
        
      case 'command_response':
        this.emit('command_response', message)
        break
        
      case 'subscription_confirmed':
        console.log('Subscribed to topic:', message.topic)
        break
        
      case 'ping':
        // Respond to ping with pong
        this.send({ type: 'pong' })
        break
        
      case 'error':
        console.error('WebSocket server error:', message.message)
        this.emit('error', message)
        break
        
      default:
        // Forward all messages to generic message handler
        this.emit('message', message)
        break
    }
  }

  subscribe(topics: string | string[]): void {
    const topicList = Array.isArray(topics) ? topics : [topics]
    topicList.forEach(topic => {
      this.send({
        type: 'subscribe',
        topic: topic
      })
    })
  }

  unsubscribe(topics: string | string[]): void {
    const topicList = Array.isArray(topics) ? topics : [topics]
    topicList.forEach(topic => {
      this.send({
        type: 'unsubscribe',
        topic: topic
      })
    })
  }

  getStatus(): void {
    this.send({ type: 'get_status' })
  }
}

export const webSocketService = new WebSocketService()
export default webSocketService

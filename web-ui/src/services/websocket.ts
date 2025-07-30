import { io, Socket } from 'socket.io-client'
import { WebSocketMessage } from '../types'

class WebSocketService {
  private socket: Socket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private eventHandlers: Map<string, Function[]> = new Map()

  connect(): void {
    if (this.socket?.connected) {
      return
    }

    const wsUrl = process.env.NODE_ENV === 'development' 
      ? 'ws://localhost:9002' 
      : `ws://${window.location.hostname}:9002`

    this.socket = io(wsUrl, {
      transports: ['websocket'],
      timeout: 5000,
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: this.reconnectDelay,
      reconnectionDelayMax: 10000,
    })

    this.socket.on('connect', () => {
      console.log('WebSocket connected')
      this.reconnectAttempts = 0
      this.emit('connect')
      
      // Subscribe to all relevant topics
      this.subscribe([
        'mower/status',
        'sensors/+',
        'weather/current',
        'weather/forecast',
        'navigation/position',
        'navigation/obstacles',
        'power/battery',
        'system/alerts'
      ])
    })

    this.socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason)
      this.emit('disconnect', reason)
    })

    this.socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error)
      this.reconnectAttempts++
      this.emit('error', error)
    })

    this.socket.on('message', (message: WebSocketMessage) => {
      this.handleMessage(message)
    })

    // Handle specific message types
    this.socket.on('mower_status', (data) => {
      this.emit('mower_status', data)
    })

    this.socket.on('sensor_data', (data) => {
      this.emit('sensor_data', data)
    })

    this.socket.on('weather_data', (data) => {
      this.emit('weather_data', data)
    })

    this.socket.on('navigation_update', (data) => {
      this.emit('navigation_update', data)
    })

    this.socket.on('notification', (data) => {
      this.emit('notification', data)
    })
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
    this.eventHandlers.clear()
  }

  subscribe(topics: string[]): void {
    if (this.socket?.connected) {
      this.socket.emit('subscribe', topics)
    }
  }

  unsubscribe(topics: string[]): void {
    if (this.socket?.connected) {
      this.socket.emit('unsubscribe', topics)
    }
  }

  send(topic: string, data: any): void {
    if (this.socket?.connected) {
      this.socket.emit('message', {
        topic,
        payload: data,
        timestamp: Date.now()
      })
    }
  }

  sendCommand(command: string, parameters?: any): Promise<any> {
    return new Promise((resolve, reject) => {
      if (!this.socket?.connected) {
        reject(new Error('WebSocket not connected'))
        return
      }

      const requestId = Date.now().toString()
      const timeout = setTimeout(() => {
        reject(new Error('Command timeout'))
      }, 10000)

      const handleResponse = (response: any) => {
        if (response.requestId === requestId) {
          clearTimeout(timeout)
          this.socket?.off('command_response', handleResponse)
          if (response.success) {
            resolve(response.data)
          } else {
            reject(new Error(response.error))
          }
        }
      }

      this.socket.on('command_response', handleResponse)
      
      this.socket.emit('command', {
        requestId,
        command,
        parameters,
        timestamp: Date.now()
      })
    })
  }

  on(event: string, handler: Function): void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, [])
    }
    this.eventHandlers.get(event)!.push(handler)
  }

  off(event: string, handler?: Function): void {
    if (!handler) {
      this.eventHandlers.delete(event)
      return
    }

    const handlers = this.eventHandlers.get(event)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }

  private emit(event: string, data?: any): void {
    const handlers = this.eventHandlers.get(event)
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(data)
        } catch (error) {
          console.error(`Error in WebSocket event handler for ${event}:`, error)
        }
      })
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    const { type, topic, payload } = message
    
    // Route message based on topic
    if (topic.startsWith('mower/')) {
      this.emit('mower_status', payload)
    } else if (topic.startsWith('sensors/')) {
      this.emit('sensor_data', { sensor: topic.split('/')[1], data: payload })
    } else if (topic.startsWith('weather/')) {
      this.emit('weather_data', payload)
    } else if (topic.startsWith('navigation/')) {
      this.emit('navigation_update', payload)
    } else if (topic.startsWith('system/alerts')) {
      this.emit('notification', {
        type: 'warning',
        title: 'System Alert',
        message: payload.message || 'System notification received'
      })
    }
  }

  get isConnected(): boolean {
    return this.socket?.connected || false
  }

  get connectionState(): 'connected' | 'disconnected' | 'connecting' | 'error' {
    if (!this.socket) return 'disconnected'
    if (this.socket.connected) return 'connected'
    if (this.socket.connecting) return 'connecting'
    return 'error'
  }
}

export const webSocketService = new WebSocketService()

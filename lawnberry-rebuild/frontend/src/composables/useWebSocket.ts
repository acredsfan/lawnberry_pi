import { ref, onUnmounted } from 'vue'
import { io, Socket } from 'socket.io-client'

export function useWebSocket(url = '/ws') {
  const socket = ref<Socket | null>(null)
  const isConnected = ref(false)
  type WSMessage = { type: string; [key: string]: unknown }
  const lastMessage = ref<WSMessage | null>(null)
  const error = ref<string | null>(null)
  const reconnecting = ref(false)
  const reconnectTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  const backoffSteps = [500, 1000, 2000, 5000, 10000]
  let backoffIndex = 0
  const subscribedTopics = new Set<string>()
  const lastCadence = ref<number | null>(null)

  const setupHandlers = () => {
    if (!socket.value) return
    socket.value.on('connect', () => {
      isConnected.value = true
      reconnecting.value = false
      backoffIndex = 0
      // Re-subscribe to topics on reconnect
      subscribedTopics.forEach((topic) => {
        emit('subscribe', { topic })
      })
      // Re-apply cadence if set
      if (lastCadence.value !== null) {
        emit('set_cadence', { cadence_hz: lastCadence.value })
      }
      console.log('WebSocket connected')
    })

    socket.value.on('disconnect', (reason) => {
      isConnected.value = false
      console.log('WebSocket disconnected:', reason)
      scheduleReconnect()
    })

    socket.value.on('error', (err) => {
      error.value = (err as any).message || 'WebSocket error'
      console.error('WebSocket error:', err)
    })

    socket.value.on('telemetry', (data) => {
      lastMessage.value = { type: 'telemetry', ...data }
    })

    socket.value.on('system_status', (data) => {
      lastMessage.value = { type: 'system_status', ...data }
    })

    socket.value.on('navigation_update', (data) => {
      lastMessage.value = { type: 'navigation_update', ...data }
    })

    socket.value.on('motor_status', (data) => {
      lastMessage.value = { type: 'motor_status', ...data }
    })

    socket.value.on('sensor_data', (data) => {
      lastMessage.value = { type: 'sensor_data', ...data }
    })

    socket.value.on('ai_update', (data) => {
      lastMessage.value = { type: 'ai_update', ...data }
    })
  }

  const scheduleReconnect = () => {
    if (reconnectTimer.value) return
    reconnecting.value = true
    const delay = backoffSteps[Math.min(backoffIndex, backoffSteps.length - 1)]
    backoffIndex = Math.min(backoffIndex + 1, backoffSteps.length - 1)
    reconnectTimer.value = setTimeout(() => {
      reconnectTimer.value = null
      void connect()
    }, delay)
  }

  const connect = async () => {
    try {
      error.value = null
      
      const token = localStorage.getItem('auth_token')
      
      socket.value = io(url, {
        auth: {
          token
        },
        transports: ['websocket', 'polling']
      })
      setupHandlers()

    } catch (err: any) {
      error.value = err.message || 'Failed to connect to WebSocket'
      throw err
    }
  }

  const disconnect = async () => {
    if (socket.value) {
      socket.value.disconnect()
      socket.value = null
      isConnected.value = false
    }
  }

  const emit = (event: string, data: any) => {
    if (socket.value && isConnected.value) {
      socket.value.emit(event, data)
    } else {
      console.warn('Socket not connected, cannot emit event:', event)
    }
  }

  // Helper to request server to change telemetry cadence
  const setCadence = (hz: number) => {
    lastCadence.value = hz
    emit('set_cadence', { cadence_hz: hz })
  }

  // Helper to subscribe to a topic on the server (for WS bridge patterns)
  const subscribeTopic = (topic: string) => {
    subscribedTopics.add(topic)
    emit('subscribe', { topic })
  }

  const subscribe = (event: string, handler: (data: any) => void) => {
    if (socket.value) {
      socket.value.on(event, handler)
    }
  }

  const unsubscribe = (event: string, handler?: (data: any) => void) => {
    if (socket.value) {
      if (handler) {
        socket.value.off(event, handler)
      } else {
        socket.value.off(event)
      }
    }
  }

  onUnmounted(() => {
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }
    disconnect()
  })

  return {
    socket,
    isConnected,
    lastMessage,
    error,
    connect,
    disconnect,
    emit,
    setCadence,
    subscribeTopic,
    subscribe,
    unsubscribe
  }
}
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SystemStatus, ConnectionStatus } from '@/types/system'
import { useWebSocket } from '@/composables/useWebSocket'

export const useSystemStore = defineStore('system', () => {
  const status = ref<SystemStatus>('unknown')
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const telemetryData = ref<any>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const { connect, disconnect, isConnected, lastMessage } = useWebSocket()

  const isOnline = computed(() => connectionStatus.value === 'connected')
  const isSystemHealthy = computed(() => status.value === 'active')

  const initialize = async () => {
    try {
      isLoading.value = true
      error.value = null
      
      // Connect to WebSocket for real-time updates
      await connect()
      
      // Watch for connection status changes
      if (isConnected.value) {
        connectionStatus.value = 'connected'
      }
      
      // Watch for telemetry messages
      if (lastMessage.value) {
        telemetryData.value = lastMessage.value
        updateSystemStatus(lastMessage.value)
      }
      
    } catch (err: any) {
      error.value = err.message || 'System initialization failed'
      connectionStatus.value = 'error'
    } finally {
      isLoading.value = false
    }
  }

  const updateSystemStatus = (data: any) => {
    if (data.type === 'system_status') {
      status.value = data.status
    } else if (data.type === 'telemetry') {
      telemetryData.value = data
      // Update system status based on telemetry health
      const isHealthy = data.sensors?.health || data.motors?.health || data.navigation?.health
      status.value = isHealthy ? 'active' : 'warning'
    }
  }

  const shutdown = async () => {
    await disconnect()
    connectionStatus.value = 'disconnected'
    status.value = 'unknown'
  }

  return {
    status,
    connectionStatus,
    telemetryData,
    isLoading,
    error,
    isOnline,
    isSystemHealthy,
    initialize,
    updateSystemStatus,
    shutdown
  }
})
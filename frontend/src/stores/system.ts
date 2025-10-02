import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SystemStatus, ConnectionStatus } from '@/types/system'
import type { 
  HardwareTelemetryStream, 
  TelemetryLatencyBadge, 
  RTKStatus, 
  IMUOrientation,
  PowerMetrics 
} from '@/types/telemetry'
import { useWebSocket } from '@/composables/useWebSocket'
import apiService from '@/services/api'

export const useSystemStore = defineStore('system', () => {
  const status = ref<SystemStatus>('unknown')
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const telemetryData = ref<any>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  
  // Telemetry-specific state
  const latencyBadge = ref<TelemetryLatencyBadge | null>(null)
  const rtkStatus = ref<RTKStatus | null>(null)
  const imuOrientation = ref<IMUOrientation | null>(null)
  const powerMetrics = ref<PowerMetrics | null>(null)
  const hardwareStreams = ref<HardwareTelemetryStream[]>([])

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

  const loadTelemetryStream = async (params?: {
    page?: number
    per_page?: number
    component_id?: string
  }) => {
    try {
      isLoading.value = true
      error.value = null
      
      const response = await apiService.getTelemetryStream(params)
      const data = response.data
      
      hardwareStreams.value = data.streams || []
      
      // Update latency badge
      if (data.latency_stats) {
        const avgLatency = data.latency_stats.avg_latency_ms
        const device = avgLatency <= 250 ? 'pi5' : 'pi4'
        const targetMs = device === 'pi5' ? 250 : 350
        
        latencyBadge.value = {
          latency_ms: avgLatency,
          status: avgLatency <= targetMs ? 'healthy' : avgLatency <= targetMs * 1.2 ? 'warning' : 'critical',
          target_ms: targetMs,
          device
        }
      }
      
      // Update RTK status
      rtkStatus.value = data.rtk_status || null
      
      // Update IMU orientation
      imuOrientation.value = data.imu_orientation || null
      
      // Extract power metrics from streams
      const powerStream = hardwareStreams.value.find(s => s.component_id === 'power')
      if (powerStream && powerStream.power_data) {
        powerMetrics.value = {
          battery: {
            voltage: powerStream.power_data.battery_voltage,
            current: powerStream.power_data.battery_current,
            power: powerStream.power_data.battery_power,
            soc_percent: powerStream.power_data.battery_soc_percent,
            health: powerStream.power_data.battery_health
          },
          solar: {
            voltage: powerStream.power_data.solar_voltage,
            current: powerStream.power_data.solar_current,
            power: powerStream.power_data.solar_power
          },
          timestamp: powerStream.timestamp
        }
      }
      
    } catch (err: any) {
      error.value = err.message || 'Failed to load telemetry stream'
    } finally {
      isLoading.value = false
    }
  }

  const exportTelemetryDiagnostic = async (params?: {
    component_id?: string
    start_time?: string
    end_time?: string
  }) => {
    try {
      isLoading.value = true
      error.value = null
      
      const response = await apiService.exportTelemetryDiagnostic(params)
      
      // Create a download link
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `telemetry-diagnostic-${new Date().toISOString()}.json`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      
    } catch (err: any) {
      error.value = err.message || 'Failed to export telemetry diagnostic'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  const pingTelemetry = async (componentId: string, sampleCount: number = 20) => {
    try {
      const response = await apiService.pingTelemetry({
        component_id: componentId,
        sample_count: sampleCount
      })
      return response.data
    } catch (err: any) {
      error.value = err.message || 'Telemetry ping failed'
      throw err
    }
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
    shutdown,
    // Telemetry state
    latencyBadge,
    rtkStatus,
    imuOrientation,
    powerMetrics,
    hardwareStreams,
    // Telemetry methods
    loadTelemetryStream,
    exportTelemetryDiagnostic,
    pingTelemetry
  }
})
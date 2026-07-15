import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { SystemStatus, ConnectionStatus } from '@/types/system'
import type {
  HardwareTelemetryStream,
  TelemetryLatencyBadge,
  RTKStatus,
  IMUOrientation,
  PowerMetrics,
} from '@/types/telemetry'
import { useWebSocket } from '@/services/websocket'
import apiService from '@/services/api'

export const useSystemStore = defineStore('system', () => {
  const status = ref<SystemStatus>('unknown')
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const telemetryData = ref<any>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const buildInfo = ref<{
    version: string
    commit_sha: string | null
    short_sha: string | null
    source: string
    started_at: string
  } | null>(null)
  const telemetrySource = ref<string | null>(null)
  const telemetryObservedAt = ref<string | null>(null)
  const lastTelemetryReceivedAt = ref<number | null>(null)
  const clockMs = ref(Date.now())
  let clockTimer: ReturnType<typeof setInterval> | null = null

  // Telemetry-specific state
  const latencyBadge = ref<TelemetryLatencyBadge | null>(null)
  const rtkStatus = ref<RTKStatus | null>(null)
  const imuOrientation = ref<IMUOrientation | null>(null)
  const powerMetrics = ref<PowerMetrics | null>(null)
  const hardwareStreams = ref<HardwareTelemetryStream[]>([])

  const { connect, disconnect, connected, subscribe, unsubscribe } = useWebSocket()

  const isOnline = computed(() => connectionStatus.value === 'connected')
  const telemetrySampleAgeSeconds = computed<number | null>(() => {
    if (telemetryObservedAt.value) {
      const observedMs = Date.parse(telemetryObservedAt.value)
      if (Number.isFinite(observedMs)) return Math.max(0, (clockMs.value - observedMs) / 1000)
    }
    return lastTelemetryReceivedAt.value === null
      ? null
      : Math.max(0, (clockMs.value - lastTelemetryReceivedAt.value) / 1000)
  })
  const telemetryFresh = computed(
    () => telemetrySampleAgeSeconds.value !== null && telemetrySampleAgeSeconds.value <= 5
  )
  const isSystemHealthy = computed(() => status.value === 'active' && telemetryFresh.value)
  const effectiveStatus = computed<SystemStatus>(() => {
    if (status.value === 'error') return 'error'
    if (!telemetryFresh.value) return 'unknown'
    return status.value
  })

  watch(
    connected,
    (isConnected) => {
      connectionStatus.value = isConnected ? 'connected' : 'disconnected'
    },
    { immediate: true }
  )

  const initialize = async () => {
    try {
      isLoading.value = true
      error.value = null

      if (clockTimer === null) {
        clockTimer = setInterval(() => {
          clockMs.value = Date.now()
        }, 1000)
      }

      try {
        const response = await apiService.get('/api/v2/system/info')
        buildInfo.value = response.data
      } catch {
        buildInfo.value = null
      }

      // Connect to WebSocket for real-time updates
      await connect()
      subscribe('telemetry.system', updateSystemStatus)
      subscribe('telemetry/updates', updateSystemStatus)
    } catch (err: any) {
      error.value = err.message || 'System initialization failed'
      connectionStatus.value = 'error'
    } finally {
      isLoading.value = false
    }
  }

  const updateSystemStatus = (data: any) => {
    if (data?.event === 'telemetry.data' && data?.data) {
      updateSystemStatus(data.data)
      return
    }

    lastTelemetryReceivedAt.value = Date.now()
    telemetrySource.value = data?.sample?.source ?? data?.source ?? null
    telemetryObservedAt.value = data?.sample?.observed_at ?? data?.timestamp ?? null

    if (data?.type === 'system_status') {
      status.value = data.status
    } else if (data?.type === 'telemetry') {
      telemetryData.value = data
      // Update system status based on telemetry health
      const isHealthy = data.sensors?.health || data.motors?.health || data.navigation?.health
      status.value = isHealthy ? 'active' : 'warning'
    } else if (
      data?.safety_state ||
      data?.position ||
      data?.battery ||
      data?.environmental ||
      data?.power
    ) {
      telemetryData.value = data
      const safety = String(data.safety_state || '').toLowerCase()
      if (
        (safety === 'nominal' || safety === 'safe' || safety === 'active') &&
        telemetryFresh.value
      ) {
        status.value = 'active'
      } else if (safety === 'emergency_stop') {
        status.value = 'error'
      } else if (safety) {
        status.value = 'warning'
      }
    }
  }

  const shutdown = async () => {
    unsubscribe('telemetry.system')
    unsubscribe('telemetry/updates')
    await disconnect()
    if (clockTimer !== null) {
      clearInterval(clockTimer)
      clockTimer = null
    }
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
      const streamItems = Array.isArray(data.streams)
        ? data.streams
        : Array.isArray(data.items)
          ? data.items
          : []

      hardwareStreams.value = streamItems.map((item: any) => ({
        ...item,
        power_data:
          item.power_data || item.metadata?.power_data || item.power || item.metadata?.power,
      }))

      // Update latency badge
      const latencyStats = data.latency_stats || data.latency_summary_ms
      if (latencyStats) {
        const avgLatency = latencyStats.avg_latency_ms ?? latencyStats.avg ?? 0
        const device = avgLatency <= 250 ? 'pi5' : 'pi4'
        const targetMs = device === 'pi5' ? 250 : 350

        latencyBadge.value = {
          latency_ms: avgLatency,
          status:
            avgLatency <= targetMs
              ? 'healthy'
              : avgLatency <= targetMs * 1.2
                ? 'warning'
                : 'critical',
          target_ms: targetMs,
          device,
        }
      }

      // Update RTK status
      rtkStatus.value = data.rtk_status || null

      // Update IMU orientation
      imuOrientation.value = data.imu_orientation || null

      // Extract power metrics from streams
      const powerStream = hardwareStreams.value.find((s) => s.component_id === 'power')
      if (powerStream && powerStream.power_data) {
        powerMetrics.value = {
          battery: {
            voltage: powerStream.power_data.battery_voltage,
            current: powerStream.power_data.battery_current,
            power: powerStream.power_data.battery_power,
            soc_percent: powerStream.power_data.battery_soc_percent,
            health: powerStream.power_data.battery_health,
          },
          solar: {
            voltage: powerStream.power_data.solar_voltage,
            current: powerStream.power_data.solar_current,
            power: powerStream.power_data.solar_power,
          },
          timestamp: powerStream.timestamp,
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
        sample_count: sampleCount,
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
    effectiveStatus,
    buildInfo,
    telemetrySource,
    telemetrySampleAgeSeconds,
    telemetryFresh,
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
    pingTelemetry,
  }
})

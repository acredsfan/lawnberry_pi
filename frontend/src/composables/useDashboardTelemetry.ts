import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'

export function useDashboardTelemetry() {
  const ws = useWebSocket()

  const batteryData = ref<Record<string, unknown> | null>(null)
  const positionData = ref<Record<string, unknown> | null>(null)
  const orientationData = ref<Record<string, unknown> | null>(null)
  const environmentalData = ref<Record<string, unknown> | null>(null)
  const systemData = ref<Record<string, unknown> | null>(null)
  const tofData = ref<Record<string, unknown> | null>(null)
  const imuData = ref<Record<string, unknown> | null>(null)
  const safetyData = ref<Record<string, unknown> | null>(null)
  const eventLog = ref<Record<string, unknown>[]>([])

  function handlePower(data: Record<string, unknown>) { batteryData.value = data }
  function handleNavigation(data: Record<string, unknown>) { positionData.value = data }
  function handleOrientation(data: Record<string, unknown>) { orientationData.value = data }
  function handleEnvironmental(data: Record<string, unknown>) { environmentalData.value = data }
  function handleSystem(data: Record<string, unknown>) { systemData.value = data }
  function handleTof(data: Record<string, unknown>) { tofData.value = data }
  function handleImu(data: Record<string, unknown>) { imuData.value = data }
  function handleSafety(data: Record<string, unknown>) { safetyData.value = data }
  function handleEvent(data: Record<string, unknown>) {
    eventLog.value = [data, ...eventLog.value].slice(0, 100)
  }

  const subscriptions: Array<[string, (d: Record<string, unknown>) => void]> = [
    ['telemetry.power', handlePower],
    ['telemetry.navigation', handleNavigation],
    ['telemetry.orientation', handleOrientation],
    ['telemetry.environmental', handleEnvironmental],
    ['telemetry.system', handleSystem],
    ['telemetry.tof', handleTof],
    ['telemetry.imu', handleImu],
    ['telemetry.safety', handleSafety],
    ['telemetry.event', handleEvent],
  ]

  onMounted(async () => {
    try {
      await ws.connect()
      ws.setCadence(5)
      subscriptions.forEach(([topic, handler]) => ws.subscribe(topic, handler))
    } catch (error) {
      console.warn('useDashboardTelemetry: WS connect failed', error)
    }
  })

  onUnmounted(() => {
    subscriptions.forEach(([topic, handler]) => ws.unsubscribe(topic, handler))
  })

  return {
    batteryData, positionData, orientationData, environmentalData,
    systemData, tofData, imuData, safetyData, eventLog,
  }
}

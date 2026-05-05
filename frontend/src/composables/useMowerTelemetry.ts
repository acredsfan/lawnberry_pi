import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/services/websocket'
import { useApiService } from '@/services/api'

export interface MowerPosition {
  lat: number
  lon: number
  accuracy: number
  heading: number | null
}

export function useMowerTelemetry() {
  const api = useApiService()
  const mowerLatLng = ref<[number, number] | null>(null)
  const gpsAccuracyMeters = ref<number | null>(null)
  const mowerHeading = ref<number | null>(null)
  const lastWsUpdateAt = ref<number>(0)

  const mowerPosition = computed<MowerPosition | null>(() => {
    if (!mowerLatLng.value) return null
    return {
      lat: mowerLatLng.value[0],
      lon: mowerLatLng.value[1],
      accuracy: gpsAccuracyMeters.value ?? 0,
      heading: mowerHeading.value,
    }
  })

  const telemetrySocket = useWebSocket('telemetry')
  let restPollTimer: number | null = null

  function handleNavigation(payload: unknown) {
    const p = payload as Record<string, unknown>
    const pos = p?.position as Record<string, unknown> | undefined
    const lat = Number(pos?.latitude)
    const lon = Number(pos?.longitude)
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      mowerLatLng.value = [lat, lon]
      const accuracy = Number(pos?.accuracy)
      gpsAccuracyMeters.value = Number.isFinite(accuracy) ? accuracy : null
      lastWsUpdateAt.value = Date.now()
    }
    const hdg = p?.nav_heading
    mowerHeading.value = hdg != null && Number.isFinite(Number(hdg)) ? Number(hdg) : null
  }

  async function pollRestFallback() {
    if (Date.now() - lastWsUpdateAt.value < 5000) return
    try {
      const res = await api.get('/api/v2/dashboard/telemetry')
      const data = res?.data as Record<string, unknown> | undefined
      const pos = data?.position as Record<string, unknown> | undefined
      const lat = Number(pos?.latitude)
      const lon = Number(pos?.longitude)
      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        mowerLatLng.value = [lat, lon]
        const acc = Number(pos?.accuracy)
        gpsAccuracyMeters.value = Number.isFinite(acc) ? acc : null
        const hdg = data?.nav_heading
        mowerHeading.value = hdg != null && Number.isFinite(Number(hdg)) ? Number(hdg) : null
        lastWsUpdateAt.value = Date.now()
      }
    } catch {
      // REST fallback is best-effort
    }
  }

  onMounted(async () => {
    try {
      await telemetrySocket.connect()
      telemetrySocket.subscribe('telemetry.navigation', handleNavigation)
    } catch (error) {
      console.warn('useMowerTelemetry: WS connect failed, using REST fallback only', error)
    }
    restPollTimer = window.setInterval(pollRestFallback, 2000)
  })

  onUnmounted(() => {
    telemetrySocket.unsubscribe('telemetry.navigation', handleNavigation)
    if (restPollTimer !== null) {
      clearInterval(restPollTimer)
      restPollTimer = null
    }
  })

  return { mowerPosition, mowerLatLng, gpsAccuracyMeters, mowerHeading }
}

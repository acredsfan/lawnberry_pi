import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/services/websocket'
import { useApiService } from '@/services/api'

export interface MowerPosition {
  lat: number
  lon: number
  accuracy: number
  heading: number | null
  positionRole: 'body_center' | 'antenna' | 'unknown'
  antenna?: {
    lat: number
    lon: number
    accuracy: number | null
  } | null
  antennaCorrectionState?: string | null
}

export function useMowerTelemetry() {
  const api = useApiService()
  const mowerLatLng = ref<[number, number] | null>(null)
  const gpsAccuracyMeters = ref<number | null>(null)
  const mowerHeading = ref<number | null>(null)
  const mowerPositionRole = ref<'body_center' | 'antenna' | 'unknown'>('unknown')
  const antennaPosition = ref<{ lat: number; lon: number; accuracy: number | null } | null>(null)
  const antennaCorrectionState = ref<string | null>(null)
  const lastWsUpdateAt = ref<number>(0)

  const mowerPosition = computed<MowerPosition | null>(() => {
    if (!mowerLatLng.value) return null
    return {
      lat: mowerLatLng.value[0],
      lon: mowerLatLng.value[1],
      accuracy: gpsAccuracyMeters.value ?? 0,
      heading: mowerHeading.value,
      positionRole: mowerPositionRole.value,
      antenna: antennaPosition.value,
      antennaCorrectionState: antennaCorrectionState.value,
    }
  })

  const telemetrySocket = useWebSocket('telemetry')
  let restPollTimer: number | null = null

  function numeric(value: unknown): number | null {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }

  function readPoint(point: unknown): { lat: number; lon: number; accuracy: number | null } | null {
    const p = point as Record<string, unknown> | undefined
    const lat = numeric(p?.latitude)
    const lon = numeric(p?.longitude)
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      return { lat: lat as number, lon: lon as number, accuracy: numeric(p?.accuracy) }
    }
    return null
  }

  function applyTelemetryPayload(payload: Record<string, unknown> | undefined) {
    if (!payload) return

    const canonicalPose = payload.canonical_pose as Record<string, unknown> | undefined
    const bodyCenter = readPoint(canonicalPose?.body_center)
    const antenna = readPoint(canonicalPose?.antenna_position)

    antennaPosition.value = antenna
    antennaCorrectionState.value =
      typeof canonicalPose?.antenna_correction_state === 'string'
        ? canonicalPose.antenna_correction_state
        : null

    const selected = bodyCenter ?? antenna ?? readPoint(payload.position)
    if (selected) {
      mowerLatLng.value = [selected.lat, selected.lon]
      gpsAccuracyMeters.value = selected.accuracy
      if (bodyCenter) {
        mowerPositionRole.value = 'body_center'
      } else if (antenna) {
        mowerPositionRole.value = 'antenna'
      } else if (payload.position_role === 'body_center' || payload.position_role === 'antenna') {
        mowerPositionRole.value = payload.position_role
      } else {
        mowerPositionRole.value = 'unknown'
      }
      lastWsUpdateAt.value = Date.now()
    }

    const heading = numeric(canonicalPose?.heading_deg ?? payload.nav_heading)
    mowerHeading.value = heading
  }

  function handleNavigation(payload: unknown) {
    applyTelemetryPayload(payload as Record<string, unknown> | undefined)
  }

  async function pollRestFallback() {
    if (Date.now() - lastWsUpdateAt.value < 5000) return
    try {
      const res = await api.get('/api/v2/dashboard/telemetry')
      const data = res?.data as Record<string, unknown> | undefined
      applyTelemetryPayload(data)
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

import { ref, computed, onUnmounted } from 'vue'
import { useApiService } from '@/services/api'

const CAMERA_RETRY_COOLDOWN_MS = 5000

export interface CameraStatusSummary {
  active: boolean
  mode: string
  fps: number | null
  client_count: number | null
}

// One client ID per page load — shared across instances intentionally so the server
// tracks a single browser client regardless of how many components mount this composable.
const cameraStreamClientId = (() => {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch { /* noop */ }
  return `client-${Math.random().toString(36).slice(2)}`
})()

export function useCameraFeed(getSessionId: () => string | null) {
  const api = useApiService()

  const cameraInfo = ref<CameraStatusSummary>({ active: false, mode: 'offline', fps: null, client_count: null })
  const cameraFrameUrl = ref<string | null>(null)
  const cameraStreamUrl = ref<string | null>(null)
  const cameraStreamUnavailable = ref(false)
  const cameraStatusMessage = ref('Initializing camera...')
  const cameraError = ref<string | null>(null)
  const cameraLastFrame = ref<string | null>(null)
  const cameraFetchInFlight = ref(false)
  const cameraStreamFailureCount = ref(0)

  let cameraFrameObjectUrl: string | null = null
  let cameraFrameTimer: number | undefined
  let cameraStatusTimer: number | undefined
  let cameraRetryTimer: number | undefined
  let cameraReconnectTimer: number | undefined
  let cameraStartRequested = false

  // Reconnect the MJPEG stream periodically so the TCP write buffer never
  // accumulates more than ~RECONNECT_INTERVAL_MS worth of stale frames.
  // The browser opens a fresh connection with an empty buffer each time.
  const STREAM_RECONNECT_INTERVAL_MS = 30_000

  const cameraIsStreaming = computed(() => Boolean(cameraStreamUrl.value))
  const cameraDisplaySource = computed(() => cameraStreamUrl.value ?? cameraFrameUrl.value)
  const cameraModeBadge = computed(() => {
    if (cameraStreamUnavailable.value) return { label: 'SNAPSHOT FALLBACK', tone: 'warning' as const }
    if (cameraIsStreaming.value) return { label: 'STREAMING', tone: 'success' as const }
    if (cameraInfo.value.active) return { label: 'SNAPSHOTS', tone: 'info' as const }
    return { label: (cameraInfo.value.mode || 'OFFLINE').toUpperCase(), tone: 'muted' as const }
  })

  function clearSnapshotTimer() {
    if (cameraFrameTimer) { window.clearInterval(cameraFrameTimer); cameraFrameTimer = undefined }
  }

  function clearCameraRetryTimer() {
    if (cameraRetryTimer) { window.clearTimeout(cameraRetryTimer); cameraRetryTimer = undefined }
  }

  function clearStreamReconnectTimer() {
    if (cameraReconnectTimer) { window.clearTimeout(cameraReconnectTimer); cameraReconnectTimer = undefined }
  }

  function scheduleStreamReconnect() {
    clearStreamReconnectTimer()
    cameraReconnectTimer = window.setTimeout(() => {
      cameraReconnectTimer = undefined
      if (cameraStreamUrl.value && !cameraStreamUnavailable.value) {
        refreshCameraStream(true)
      }
    }, STREAM_RECONNECT_INTERVAL_MS)
  }

  function applyCameraFrameUrl(nextUrl: string | null, { revokeExisting = true } = {}) {
    if (revokeExisting && cameraFrameObjectUrl) {
      URL.revokeObjectURL(cameraFrameObjectUrl)
      cameraFrameObjectUrl = null
    }
    cameraFrameUrl.value = nextUrl
  }

  function buildCameraStreamUrl(forceRefresh = false) {
    if (cameraStreamUnavailable.value) return null
    const params = new URLSearchParams()
    params.set('client', cameraStreamClientId)
    const sid = getSessionId()
    if (sid) params.set('session_id', sid)
    if (forceRefresh) params.set('ts', Date.now().toString(36))
    return `/api/v2/camera/stream.mjpeg?${params.toString()}`
  }

  function refreshCameraStream(forceRefresh = false, resetFailures = false) {
    const nextUrl = buildCameraStreamUrl(forceRefresh)
    if (!nextUrl) return
    if (resetFailures) cameraStreamFailureCount.value = 0
    cameraStreamUrl.value = nextUrl
    cameraStatusMessage.value = 'Connecting to stream...'
  }

  function startSnapshotFallback(message?: string) {
    cameraStreamUrl.value = null
    clearStreamReconnectTimer()
    if (message) cameraStatusMessage.value = message
    clearSnapshotTimer()
    void fetchCameraFrame()
    cameraFrameTimer = window.setInterval(fetchCameraFrame, 2000)
  }

  function scheduleCameraStreamRetry(delayMs = CAMERA_RETRY_COOLDOWN_MS) {
    if (!cameraStreamUnavailable.value) { clearCameraRetryTimer(); return }
    clearCameraRetryTimer()
    cameraRetryTimer = window.setTimeout(() => void attemptCameraStreamRecovery(), delayMs)
  }

  async function attemptCameraStreamRecovery() {
    clearCameraRetryTimer()
    if (!cameraStreamUnavailable.value) return
    try {
      const streaming = await ensureCameraStreaming()
      if (streaming) {
        cameraStreamUnavailable.value = false
        refreshCameraStream(true, true)
        return
      }
    } catch { /* noop */ }
    scheduleCameraStreamRetry()
  }

  function handleCameraStreamLoad() {
    cameraError.value = null
    cameraStatusMessage.value = 'Streaming...'
    cameraStreamFailureCount.value = 0
    cameraStreamUnavailable.value = false
    clearCameraRetryTimer()
    scheduleStreamReconnect()
  }

  function handleCameraStreamError() {
    cameraStreamFailureCount.value += 1
    if (cameraStreamFailureCount.value <= 1) {
      refreshCameraStream(true)
      return
    }
    cameraStreamUnavailable.value = true
    cameraError.value = 'Camera stream unavailable'
    startSnapshotFallback('Camera stream unavailable – using snapshots...')
    scheduleCameraStreamRetry()
  }

  function normalizeCameraStatusPayload(payload: unknown) {
    if (!payload || typeof payload !== 'object') return null
    const p = payload as Record<string, unknown>
    const data = p?.status === 'success' && p?.data ? p.data as Record<string, unknown> : p
    if (!data || typeof data !== 'object') return null
    const d = data as Record<string, unknown>
    const statistics = (typeof d.statistics === 'object' && d.statistics !== null ? d.statistics : {}) as Record<string, unknown>
    const fpsCandidate = statistics.current_fps ?? statistics.fps ?? d.fps ?? null
    const lastFrameCandidate = d.last_frame_time ?? d.last_frame ?? d.capture_ts ?? null
    const active = Boolean(d.is_active ?? d.active ?? d.streaming)
    return {
      active,
      mode: (typeof d.mode === 'string' ? d.mode : undefined) ?? (d.sim_mode ? 'simulation' : (active ? 'streaming' : 'offline')),
      fps: typeof fpsCandidate === 'number' ? Number(fpsCandidate) : null,
      client_count: typeof d.client_count === 'number' ? Number(d.client_count) : null,
      last_frame_time: typeof lastFrameCandidate === 'string' ? lastFrameCandidate : null,
    }
  }

  async function fetchCameraStatus() {
    try {
      const response = await api.get('/api/v2/camera/status')
      const data = normalizeCameraStatusPayload(response.data)
      if (data) {
        cameraInfo.value = {
          active: Boolean(data.active),
          mode: data.mode || 'offline',
          fps: typeof data.fps === 'number' ? Number(data.fps) : null,
          client_count: typeof data.client_count === 'number' ? Number(data.client_count) : null,
        }
        if (!cameraInfo.value.active && cameraStreamUrl.value) {
          startSnapshotFallback('Camera idle')
        } else if (cameraInfo.value.active && !cameraStreamUrl.value && !cameraStartRequested && !cameraStreamUnavailable.value) {
          clearSnapshotTimer()
          refreshCameraStream(true, true)
        }
        if (data.last_frame_time && !cameraLastFrame.value) cameraLastFrame.value = data.last_frame_time
        cameraError.value = null
        return data
      }
    } catch { cameraError.value = 'Unable to reach camera service' }
    return null
  }

  async function ensureCameraStreaming() {
    const status = await fetchCameraStatus()
    if (status?.active) return true
    if (cameraStartRequested) return cameraInfo.value.active
    cameraStartRequested = true
    try {
      await api.post('/api/v2/camera/start')
    } catch {
      cameraError.value = 'Failed to start camera stream'
    } finally {
      await fetchCameraStatus()
      cameraStartRequested = false
    }
    return cameraInfo.value.active
  }

  async function fetchCameraFrame() {
    if (cameraFetchInFlight.value) return
    cameraFetchInFlight.value = true
    try {
      const response = await api.get('/api/v2/camera/frame', {
        responseType: 'blob',
        headers: { 'Cache-Control': 'no-cache', 'X-Client-Id': cameraStreamClientId },
      })
      const contentType = String(response.headers?.['content-type'] || response.data?.type || '')
      if (response.data instanceof Blob && contentType.startsWith('image/')) {
        if (cameraFrameObjectUrl) { URL.revokeObjectURL(cameraFrameObjectUrl); cameraFrameObjectUrl = null }
        const objectUrl = URL.createObjectURL(response.data)
        cameraFrameObjectUrl = objectUrl
        cameraFrameUrl.value = objectUrl
        cameraStatusMessage.value = 'Snapshots...'
        cameraError.value = null
        cameraLastFrame.value = new Date().toISOString()
      }
    } catch { cameraError.value = 'Camera frame request failed' } finally {
      cameraFetchInFlight.value = false
    }
  }

  function resetCameraState() {
    cameraStreamUrl.value = null
    applyCameraFrameUrl(null)
    cameraStatusMessage.value = 'Initializing camera...'
    cameraError.value = null
    cameraLastFrame.value = null
    cameraStreamFailureCount.value = 0
    cameraStreamUnavailable.value = false
    clearCameraRetryTimer()
    cameraInfo.value = { active: false, mode: 'offline', fps: null, client_count: null }
  }

  async function startCameraFeed(forceReconnect = false) {
    if (!forceReconnect && (cameraIsStreaming.value || cameraFrameTimer || cameraStatusTimer)) return
    if (cameraStatusTimer) { window.clearInterval(cameraStatusTimer); cameraStatusTimer = undefined }
    clearSnapshotTimer()
    resetCameraState()
    const streaming = await ensureCameraStreaming()
    if (streaming && !cameraStreamUnavailable.value) {
      refreshCameraStream(true, true)
      clearSnapshotTimer()
    } else {
      cameraStreamUnavailable.value = true
      startSnapshotFallback(cameraError.value || 'Camera warming up...')
      scheduleCameraStreamRetry()
    }
    if (!cameraStatusTimer) cameraStatusTimer = window.setInterval(fetchCameraStatus, 6000)
  }

  function stopCameraFeed() {
    clearSnapshotTimer()
    clearCameraRetryTimer()
    clearStreamReconnectTimer()
    if (cameraStatusTimer) { window.clearInterval(cameraStatusTimer); cameraStatusTimer = undefined }
    cameraStartRequested = false
    cameraFetchInFlight.value = false
    cameraStreamUrl.value = null
    cameraStreamFailureCount.value = 0
    applyCameraFrameUrl(null)
    cameraLastFrame.value = null
    cameraError.value = null
    cameraStatusMessage.value = 'Camera paused'
    cameraStreamUnavailable.value = false
    cameraInfo.value = { active: false, mode: 'offline', fps: null, client_count: null }
  }

  async function retryCameraFeed() {
    stopCameraFeed()
    cameraStreamFailureCount.value = 0
    cameraStreamUnavailable.value = false
    await startCameraFeed(true)
  }

  const exposed = {
    cameraInfo, cameraFrameUrl, cameraStreamUrl, cameraStreamUnavailable,
    cameraStatusMessage, cameraError, cameraLastFrame, cameraFetchInFlight,
    cameraStreamFailureCount, cameraIsStreaming, cameraDisplaySource, cameraModeBadge,
    startCameraFeed, stopCameraFeed, retryCameraFeed,
    handleCameraStreamLoad, handleCameraStreamError,
    fetchCameraStatus,
  }

  onUnmounted(() => exposed.stopCameraFeed())

  return exposed
}

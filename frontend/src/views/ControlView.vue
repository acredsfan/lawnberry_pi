<template>
  <div class="control-view">
    <div class="page-header">
      <h1>Manual Control</h1>
      <p class="text-muted">Direct manual operation and emergency controls</p>
    </div>

    <!-- Security Gate -->
    <div v-if="!isControlUnlocked" class="security-gate">
      <div class="card security-card">
        <div class="card-header">
          <h3>🔒 Control Access Required</h3>
        </div>
        <div class="card-body">
          <div class="security-info">
            <p>Manual control access requires additional authentication based on your security level:</p>
            <div class="security-level">
              <strong>Current Security Level:</strong> 
              <span class="level-badge" :class="`level-${securityConfig.auth_level}`">
                {{ formatSecurityLevel(securityConfig.auth_level) }}
              </span>
            </div>
          </div>

          <!-- Authentication Methods -->
          <div class="auth-methods">
            <!-- Password Verification -->
            <div v-if="securityConfig.auth_level === 'password'" class="auth-method">
              <label for="control-auth-password">Confirm Password</label>
              <input 
                id="control-auth-password"
                v-model="authForm.password"
                type="password" 
                class="form-control"
                placeholder="Enter your password"
                @keyup.enter="authenticateControl"
              >
            </div>

            <!-- TOTP Verification -->
            <div v-else-if="securityConfig.auth_level === 'totp'" class="auth-method">
              <label for="control-auth-totp">Enter TOTP Code</label>
              <input 
                id="control-auth-totp"
                v-model="authForm.totpCode"
                type="text" 
                class="form-control totp-input"
                placeholder="000000"
                maxlength="6"
                @keyup.enter="authenticateControl"
              >
              <small class="form-text text-muted">
                Use your authenticator app (Google Authenticator, Authy, etc.)
              </small>
            </div>

            <!-- Google Auth -->
            <div v-else-if="securityConfig.auth_level === 'google'" class="auth-method">
              <button class="btn btn-google" @click="authenticateWithGoogle">
                <span class="google-icon">🔑</span>
                Authenticate with Google
              </button>
            </div>

            <!-- Cloudflare Tunnel Auth -->
            <div v-else-if="securityConfig.auth_level === 'cloudflare'" class="auth-method">
              <div class="info-panel">
                <p>Authentication is handled by Cloudflare Access.</p>
                <p>You should already be authenticated if accessing via Cloudflare tunnel.</p>
              </div>
              <button class="btn btn-primary" @click="verifyCloudflareAuth">
                Verify Access
              </button>
            </div>
          </div>

          <div class="auth-actions" v-if="securityConfig.auth_level !== 'cloudflare'">
            <button 
              class="btn btn-primary" 
              :disabled="authenticating || !canAuthenticate"
              @click="authenticateControl"
            >
              {{ authenticating ? 'Verifying...' : 'Unlock Control' }}
            </button>
          </div>

          <div v-if="authError" class="alert alert-danger">
            {{ authError }}
          </div>
        </div>
      </div>
    </div>

    <!-- Main Control Interface (shown when unlocked) -->
    <div v-else class="control-interface">
      <!-- Control Status -->
      <div class="control-status">
        <div class="status-indicator" :class="systemStatus">
          <div class="status-light" />
          <span>{{ formatSystemStatus(systemStatus) }}</span>
        </div>
        
        <div class="session-info">
          <small>Control session expires in {{ formatTimeRemaining(sessionTimeRemaining) }}</small>
          <button class="btn btn-sm btn-secondary" @click="lockControl">
            🔒 Lock Control
          </button>
        </div>
      </div>

      <!-- Emergency Stop -->
      <div class="emergency-section">
        <button 
          class="btn btn-emergency" 
          :disabled="performing"
          @click="emergencyStop"
        >
          🛑 EMERGENCY STOP
        </button>
      </div>

      <!-- Live Camera Feed -->
      <div class="card">
        <div class="card-header">
          <h3>Live Camera Feed</h3>
        </div>
        <div class="card-body">
          <div class="camera-feed" :class="{ 'camera-feed-error': cameraError }">
            <img
              v-if="cameraDisplaySource"
              :src="cameraDisplaySource"
              alt="Live mower camera feed"
              class="camera-frame"
              :class="{ 'camera-frame--stream': cameraIsStreaming }"
              @load="handleCameraStreamLoad"
              @error="handleCameraStreamError"
            >
            <div v-else class="camera-placeholder">
              <p>{{ cameraStatusMessage }}</p>
              <button
                v-if="cameraError"
                class="btn btn-sm btn-secondary"
                @click="retryCameraFeed"
              >
                Retry
              </button>
            </div>
            <div class="camera-badge">
              {{ cameraInfo.mode ? cameraInfo.mode.toUpperCase() : 'OFFLINE' }}
            </div>
          </div>
          <div class="camera-meta">
            <span :class="{ 'camera-meta-active': cameraInfo.active }">
              {{ cameraIsStreaming ? 'Streaming' : (cameraInfo.active ? 'Snapshots' : 'Idle') }}
            </span>
            <span>FPS: {{ formatCameraFps(cameraInfo.fps) }}</span>
            <span>Last frame: {{ formatCameraTimestamp(cameraLastFrame) }}</span>
            <span>Clients: {{ cameraInfo.client_count ?? '0' }}</span>
          </div>
        </div>
      </div>

      <!-- Movement Controls -->
      <div class="card">
        <div class="card-header">
          <h3>Movement Controls</h3>
        </div>
        <div class="card-body">
          <div class="movement-layout">
            <div class="joystick-column">
              <VirtualJoystick
                ref="joystickRef"
                class="joystick-component"
                :disabled="!canMove"
                :dead-zone="0.12"
                @change="handleJoystickChange"
                @end="handleJoystickEnd"
              />
              <small class="joystick-hint">Drag to drive • Release or tap stop to halt</small>
            </div>
            <div class="movement-actions">
              <button
                class="btn btn-danger stop-button"
                :disabled="!isControlUnlocked"
                @click="handleStopButton"
              >
                🛑 Stop Motors
              </button>
              <div class="movement-readout">
                <span>Linear: {{ formatCommandValue(activeDriveVector.linear) }}</span>
                <span>Angular: {{ formatCommandValue(activeDriveVector.angular) }}</span>
              </div>
              <div v-if="joystickEngaged" class="movement-status active">Joystick engaged</div>
              <div v-else class="movement-status">Joystick idle</div>
            </div>
          </div>

          <div class="speed-control">
            <label>Speed: {{ speedLevel }}%</label>
            <input 
              v-model.number="speedLevel"
              type="range" 
              min="10" 
              max="100" 
              step="10"
              class="speed-slider"
            >
          </div>
        </div>
      </div>

      <!-- Mowing Controls -->
      <div class="card">
        <div class="card-header">
          <h3>Mowing Controls</h3>
        </div>
        <div class="card-body">
          <div class="mowing-controls">
            <button 
              class="btn" 
              :class="mowingActive ? 'btn-warning' : 'btn-success'"
              :disabled="performing"
              @click="toggleMowing"
            >
              {{ mowingActive ? '⏹️ Stop Mowing' : '▶️ Start Mowing' }}
            </button>
          </div>
        </div>
      </div>

      <!-- System Controls -->
      <div class="card">
        <div class="card-header">
          <h3>System Controls</h3>
        </div>
        <div class="card-body">
          <div class="system-controls">
            <button class="btn btn-info" :disabled="performing" @click="returnToBase">
              🏠 Return to Base
            </button>
            
            <button class="btn btn-warning" :disabled="performing" @click="pauseSystem">
              ⏸️ Pause System
            </button>
            
            <button class="btn btn-success" :disabled="performing" @click="resumeSystem">
              ▶️ Resume System
            </button>
          </div>
        </div>
      </div>

      <!-- Live Telemetry -->
      <div class="card">
        <div class="card-header">
          <h3>Live Status</h3>
        </div>
        <div class="card-body">
          <div class="telemetry-grid">
            <div class="telemetry-item">
              <label>Battery</label>
              <div class="value">{{ telemetry.battery?.percentage?.toFixed(1) || 'N/A' }}%</div>
            </div>
            <div class="telemetry-item">
              <label>GPS</label>
              <div class="value">{{ telemetry.position?.latitude ? 'LOCKED' : 'SEARCHING' }}</div>
            </div>
            <div class="telemetry-item">
              <label>Speed</label>
              <div class="value">{{ displaySpeed }} {{ speedUnit }}</div>
            </div>
            <div class="telemetry-item">
              <label>Safety</label>
              <div class="value" :class="`safety-${telemetry.safety_state}`">
                {{ telemetry.safety_state?.toUpperCase() || 'UNKNOWN' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessage" class="alert" :class="statusSuccess ? 'alert-success' : 'alert-danger'">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import axios, { type AxiosError } from 'axios'
import { storeToRefs } from 'pinia'
import { useControlStore } from '@/stores/control'
import { useApiService } from '@/services/api'
import { useToastStore } from '@/stores/toast'
import { usePreferencesStore } from '@/stores/preferences'
import VirtualJoystick from '@/components/ui/VirtualJoystick.vue'

interface ManualControlSecurityConfig {
  auth_level: 'password' | 'totp' | 'google' | 'cloudflare'
  session_timeout_minutes: number
  require_https: boolean
  auto_lock_manual_control: boolean
}

interface ManualControlSession {
  session_id: string
  expires_at?: string
}

interface ControlTelemetry {
  battery?: { percentage?: number; voltage?: number | null }
  position?: { latitude?: number | null; longitude?: number | null }
  safety_state?: string
  velocity?: { linear?: { x?: number | null } }
  telemetry_source?: 'hardware' | 'simulated' | 'unknown'
  camera?: CameraStatusSummary
}

interface CameraStatusSummary {
  active: boolean
  mode: string
  fps: number | null
  client_count: number | null
}

const MOVEMENT_DURATION_MS = 160
const MOVEMENT_REPEAT_INTERVAL_MS = 120
const CAMERA_RETRY_COOLDOWN_MS = 5000
const JOYSTICK_REASON = 'manual-joystick'

const control = useControlStore()
const api = useApiService()
const toast = useToastStore()
const preferences = usePreferencesStore()

preferences.ensureInitialized()
const { unitSystem } = storeToRefs(preferences)

// Store-backed state
const lockout = computed(() => control.lockout)
const lockoutReason = computed(() => control.lockoutReason)
const remediationLink = computed(() => control.remediationLink)
const lastEcho = computed(() => control.lastEcho)
const isLoading = computed(() => control.isLoading)
const lastCommandResult = computed(() => control.lastCommandResult)

// Manual control security configuration and authentication state
const securityConfig = ref<ManualControlSecurityConfig>({
  auth_level: 'password',
  session_timeout_minutes: 15,
  require_https: false,
  auto_lock_manual_control: true
})

const isControlUnlocked = ref(false)
const authenticating = ref(false)
const authError = ref('')
const authForm = reactive({
  password: '',
  totpCode: ''
})

const session = ref<ManualControlSession | null>(null)
const sessionTimeRemaining = ref(0)
let sessionTimer: number | undefined
let cloudflareAutoVerificationAttempted = false

// UI state
const statusMessage = ref('')
const statusSuccess = ref(false)
const performing = ref(false)
const systemStatus = ref('unknown')
const telemetry = ref<ControlTelemetry>({ safety_state: 'unknown', telemetry_source: 'unknown' })
const currentSpeed = ref(0)
const displaySpeed = computed(() => {
  const value = Number(currentSpeed.value)
  if (!Number.isFinite(value)) {
    return '0.0'
  }
  const converted = unitSystem.value === 'imperial' ? value * 2.23694 : value
  return converted.toFixed(1)
})
const speedUnit = computed(() => (unitSystem.value === 'imperial' ? 'mph' : 'm/s'))
const mowingActive = ref(false)
const speedLevel = ref(50)

const cameraInfo = reactive<CameraStatusSummary>({
  active: false,
  mode: 'offline',
  fps: null,
  client_count: null
})
const cameraFrameUrl = ref<string | null>(null)
const cameraStreamUrl = ref<string | null>(null)
const cameraStreamUnavailable = ref(false)
const cameraStatusMessage = ref('Initializing camera…')
const cameraError = ref<string | null>(null)
const cameraLastFrame = ref<string | null>(null)
const cameraFetchInFlight = ref(false)
const cameraStreamFailureCount = ref(0)
const cameraStreamClientId = (() => {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch (error) {
    /* noop */
  }
  return `client-${Math.random().toString(36).slice(2)}`
})()
let cameraFrameTimer: number | undefined
let cameraStatusTimer: number | undefined
let cameraRetryTimer: number | undefined
let cameraStartRequested = false

interface JoystickHandle {
  reset: () => void
  setVector: (vector: { x: number; y: number }) => void
}

interface DriveCommandPayload {
  session_id: string
  vector: { linear: number; angular: number }
  duration_ms: number
  reason: string
  max_speed_limit: number
}

interface QueueDriveCommandOptions {
  immediate?: boolean
}

const joystickRef = ref<JoystickHandle | null>(null)
const lastJoystickVector = ref({ x: 0, y: 0 })
const joystickEngaged = ref(false)
const activeDriveVector = ref({ linear: 0, angular: 0 })
let movementRepeatTimer: number | undefined
let currentDriveReason = JOYSTICK_REASON
let driveDispatchPromise: Promise<void> | null = null
let driveCommandActive = false
let pendingDrivePayload: DriveCommandPayload | null = null

// Derived state
const canAuthenticate = computed(() => {
  switch (securityConfig.value.auth_level) {
    case 'password':
      return authForm.password.trim().length > 0
    case 'totp':
      return authForm.password.trim().length > 0 && authForm.totpCode.trim().length === 6
    case 'google':
      return true
    case 'cloudflare':
      return true
    default:
      return false
  }
})

const canMove = computed(() =>
  isControlUnlocked.value && !performing.value && !lockout.value
)

const canSubmitBlade = computed(() =>
  isControlUnlocked.value && !performing.value && !lockout.value
)

const cameraDisplaySource = computed(() => cameraStreamUrl.value ?? cameraFrameUrl.value)
const cameraIsStreaming = computed(() => Boolean(cameraStreamUrl.value))

// Helpers
function mapSecurityLevel(value: unknown): ManualControlSecurityConfig['auth_level'] {
  if (typeof value === 'string') {
    switch (value) {
      case 'password_only':
      case 'password':
        return 'password'
      case 'password_totp':
      case 'totp':
        return 'totp'
      case 'google_auth':
      case 'google':
        return 'google'
      case 'cloudflare_tunnel_auth':
      case 'tunnel':
      case 'cloudflare':
        return 'cloudflare'
      default:
        return 'password'
    }
  }

  if (typeof value === 'number') {
    if (value >= 4) return 'cloudflare'
    if (value === 3) return 'google'
    if (value === 2) return 'totp'
    return 'password'
  }

  return 'password'
}

function formatSecurityLevel(level: ManualControlSecurityConfig['auth_level']) {
  switch (level) {
    case 'password':
      return 'Password'
    case 'totp':
      return 'Password + TOTP'
    case 'google':
      return 'Google OAuth'
    case 'cloudflare':
      return 'Cloudflare Access'
    default:
      return 'Unknown'
  }
}

function formatSystemStatus(status: string) {
  switch (status?.toLowerCase()) {
    case 'nominal':
    case 'ok':
    case 'ready':
      return 'Ready'
    case 'active':
    case 'running':
      return 'Active'
    case 'caution':
    case 'warning':
      return 'Caution'
    case 'emergency':
    case 'fault':
      return 'Emergency Stop'
    default:
      return 'Unknown'
  }
}

function formatTimeRemaining(seconds: number) {
  if (!seconds || seconds <= 0) {
    return 'expired'
  }
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins === 0) {
    return `${secs}s`
  }
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

function formatCameraFps(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value) || value <= 0) {
    return '—'
  }
  return value.toFixed(1)
}

function formatCameraTimestamp(timestamp: string | null | undefined) {
  if (!timestamp) {
    return 'No frames yet'
  }
  const parsed = new Date(timestamp)
  if (Number.isNaN(parsed.getTime())) {
    return 'No frames yet'
  }
  return parsed.toLocaleTimeString()
}

function showStatus(message: string, success: boolean, timeout = 4000) {
  statusMessage.value = message
  statusSuccess.value = success
  if (timeout > 0) {
    window.setTimeout(() => {
      statusMessage.value = ''
    }, timeout)
  }
}

function resetCameraState() {
  cameraStreamUrl.value = null
  cameraFrameUrl.value = null
  cameraStatusMessage.value = 'Initializing camera…'
  cameraError.value = null
  cameraLastFrame.value = null
  cameraStreamFailureCount.value = 0
  cameraStreamUnavailable.value = false
  clearCameraRetryTimer()
  Object.assign(cameraInfo, {
    active: false,
    mode: 'offline',
    fps: null,
    client_count: null
  })
}

function buildCameraStreamUrl(forceRefresh = false) {
  if (cameraStreamUnavailable.value) {
    return null
  }
  const params = new URLSearchParams()
  params.set('client', cameraStreamClientId)
  const sessionId = session.value?.session_id
  if (sessionId) {
    params.set('session_id', sessionId)
  }
  if (forceRefresh) {
    params.set('ts', Date.now().toString(36))
  }
  return `/api/v2/camera/stream.mjpeg?${params.toString()}`
}

function refreshCameraStream(forceRefresh = false, resetFailures = false) {
  const nextUrl = buildCameraStreamUrl(forceRefresh)
  if (!nextUrl) {
    return
  }
  if (resetFailures) {
    cameraStreamFailureCount.value = 0
  }
  cameraStreamUrl.value = nextUrl
  cameraStatusMessage.value = 'Connecting to stream…'
}

function clearSnapshotTimer() {
  if (cameraFrameTimer) {
    window.clearInterval(cameraFrameTimer)
    cameraFrameTimer = undefined
  }
}

function clearCameraRetryTimer() {
  if (cameraRetryTimer) {
    window.clearTimeout(cameraRetryTimer)
    cameraRetryTimer = undefined
  }
}

async function attemptCameraStreamRecovery() {
  clearCameraRetryTimer()
  if (!cameraStreamUnavailable.value) {
    return
  }
  try {
    const streaming = await ensureCameraStreaming()
    if (streaming) {
      cameraStreamUnavailable.value = false
      refreshCameraStream(true, true)
      return
    }
  } catch (error) {
    /* noop – retry will be scheduled */
  }
  scheduleCameraStreamRetry()
}

function scheduleCameraStreamRetry(delayMs = CAMERA_RETRY_COOLDOWN_MS) {
  if (!cameraStreamUnavailable.value) {
    clearCameraRetryTimer()
    return
  }
  clearCameraRetryTimer()
  cameraRetryTimer = window.setTimeout(() => {
    void attemptCameraStreamRecovery()
  }, delayMs)
}

function startSnapshotFallback(message?: string) {
  cameraStreamUrl.value = null
  if (message) {
    cameraStatusMessage.value = message
  }
  clearSnapshotTimer()
  void fetchCameraFrame()
  cameraFrameTimer = window.setInterval(fetchCameraFrame, 2000)
}

function handleCameraStreamLoad() {
  cameraError.value = null
  cameraStatusMessage.value = 'Streaming…'
  cameraStreamFailureCount.value = 0
  cameraStreamUnavailable.value = false
  clearCameraRetryTimer()
}

function handleCameraStreamError() {
  cameraStreamFailureCount.value += 1
  if (cameraStreamFailureCount.value <= 1) {
    refreshCameraStream(true)
    return
  }
  cameraStreamUnavailable.value = true
  cameraError.value = 'Camera stream unavailable'
  startSnapshotFallback('Camera stream unavailable – using snapshots…')
  scheduleCameraStreamRetry()
}

function updateSessionTimer(expiresAt?: string) {
  if (sessionTimer) {
    window.clearInterval(sessionTimer)
    sessionTimer = undefined
  }

  const expiration = expiresAt ? new Date(expiresAt).getTime() : null

  if (!expiration) {
    sessionTimeRemaining.value = securityConfig.value.session_timeout_minutes * 60
    return
  }

  const tick = () => {
    const remaining = Math.max(0, Math.floor((expiration - Date.now()) / 1000))
    sessionTimeRemaining.value = remaining
    if (remaining === 0) {
      lockControl()
      showStatus('Manual control session expired', false)
      toast.show('Manual control session expired', 'warning', 4000)
    }
  }

  tick()
  sessionTimer = window.setInterval(tick, 1000)
}

async function fetchCameraStatus() {
  try {
    const response = await api.get('/api/v2/camera/status')
    const payload = response.data
    if (payload?.status === 'success' && payload.data) {
      const data = payload.data
      Object.assign(cameraInfo, {
        active: Boolean(data.is_active),
        mode: data.mode || 'offline',
        fps: typeof data.statistics?.current_fps === 'number'
          ? Number(data.statistics.current_fps)
          : null,
        client_count: typeof data.client_count === 'number'
          ? Number(data.client_count)
          : null
      })
      if (!cameraInfo.active && cameraStreamUrl.value) {
        startSnapshotFallback('Camera idle')
      } else if (
        cameraInfo.active &&
        !cameraStreamUrl.value &&
        !cameraStartRequested &&
        !cameraStreamUnavailable.value
      ) {
        clearSnapshotTimer()
        refreshCameraStream(true, true)
      }
      if (data.last_frame_time && !cameraLastFrame.value) {
        cameraLastFrame.value = data.last_frame_time
      }
      cameraError.value = null
      if (cameraInfo.active && !cameraFrameUrl.value) {
        cameraStatusMessage.value = 'Waiting for frames…'
      }
      return data
    }
    if (payload?.error) {
      cameraError.value = payload.error
      cameraStatusMessage.value = payload.error
    }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 429) {
      cameraError.value = 'Camera service temporarily busy'
      cameraStatusMessage.value = 'Camera requests throttled – retrying…'
    } else {
      cameraError.value = 'Unable to reach camera service'
      cameraStatusMessage.value = 'Camera offline'
    }
  }
  return null
}

async function ensureCameraStreaming() {
  const status = await fetchCameraStatus()
  if (status?.is_active) {
    if (cameraStreamUnavailable.value) {
      return false
    }
    return true
  }

  if (cameraStartRequested) {
    return cameraInfo.active
  }

  cameraStartRequested = true
  try {
    const response = await api.post('/api/v2/camera/start')
    const payload = response.data
    if (payload?.status === 'error' && payload?.error) {
      cameraError.value = payload.error
      cameraStatusMessage.value = payload.error
    }
  } catch (error) {
    cameraError.value = 'Failed to start camera stream'
    cameraStatusMessage.value = 'Camera offline'
  } finally {
    await fetchCameraStatus()
    cameraStartRequested = false
  }

  return cameraInfo.active
}

async function fetchCameraFrame() {
  if (cameraFetchInFlight.value) {
    return
  }

  cameraFetchInFlight.value = true
  try {
    const response = await api.get('/api/v2/camera/frame')
    const payload = response.data
    if (payload?.status === 'success' && payload.data) {
      const frame = payload.data
      const format = typeof frame?.metadata?.format === 'string'
        ? String(frame.metadata.format).toLowerCase()
        : 'jpeg'
      if (frame?.data) {
        cameraFrameUrl.value = `data:image/${format};base64,${frame.data}`
        cameraStatusMessage.value = 'Snapshots…'
        cameraError.value = null
      } else {
        cameraStatusMessage.value = 'Waiting for frame data…'
      }
      if (frame?.metadata?.timestamp) {
        cameraLastFrame.value = frame.metadata.timestamp
      }
    } else if (payload?.error === 'No frame available') {
      cameraStatusMessage.value = 'Camera warming up…'
    } else if (payload?.error) {
      cameraError.value = payload.error
      cameraStatusMessage.value = payload.error
    }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 429) {
      cameraError.value = 'Camera frames throttled'
      cameraStatusMessage.value = 'Cooling down camera requests…'
    } else {
      cameraError.value = 'Camera frame request failed'
      cameraStatusMessage.value = 'Camera offline'
    }
  } finally {
    cameraFetchInFlight.value = false
  }
}

async function startCameraFeed(forceReconnect = false) {
  if (!forceReconnect && (cameraIsStreaming.value || cameraFrameTimer || cameraStatusTimer)) {
    return
  }

  if (cameraStatusTimer) {
    window.clearInterval(cameraStatusTimer)
    cameraStatusTimer = undefined
  }
  clearSnapshotTimer()
  resetCameraState()

  const streaming = await ensureCameraStreaming()
  if (streaming && !cameraStreamUnavailable.value) {
    refreshCameraStream(true, true)
    clearSnapshotTimer()
  } else {
    startSnapshotFallback(cameraError.value || 'Camera warming up…')
    cameraStreamUnavailable.value = true
    scheduleCameraStreamRetry()
  }

  if (!cameraStatusTimer) {
    cameraStatusTimer = window.setInterval(fetchCameraStatus, 6000)
  }
}

function stopCameraFeed() {
  clearSnapshotTimer()
  clearCameraRetryTimer()
  if (cameraStatusTimer) {
    window.clearInterval(cameraStatusTimer)
    cameraStatusTimer = undefined
  }
  cameraStartRequested = false
  cameraFetchInFlight.value = false
  cameraStreamUrl.value = null
  cameraStreamFailureCount.value = 0
  cameraFrameUrl.value = null
  cameraLastFrame.value = null
  cameraError.value = null
  cameraStatusMessage.value = 'Camera paused'
  cameraStreamUnavailable.value = false
  Object.assign(cameraInfo, {
    active: false,
    mode: 'offline',
    fps: null,
    client_count: null
  })
}

async function retryCameraFeed() {
  stopCameraFeed()
  cameraStreamFailureCount.value = 0
  cameraStreamUnavailable.value = false
  await startCameraFeed(true)
}

async function loadSecurityConfig() {
  try {
    const response = await api.get('/api/v2/settings/security')
    const data = response.data ?? {}
    securityConfig.value = {
      auth_level: mapSecurityLevel(data.security_level ?? data.level),
      session_timeout_minutes: data.session_timeout_minutes ?? securityConfig.value.session_timeout_minutes,
      require_https: Boolean(data.require_https ?? securityConfig.value.require_https),
      auto_lock_manual_control: Boolean(data.auto_lock_manual_control ?? securityConfig.value.auto_lock_manual_control)
    }

    if (securityConfig.value.auth_level === 'cloudflare' && !cloudflareAutoVerificationAttempted) {
      cloudflareAutoVerificationAttempted = true
      await verifyCloudflareAuth()
    }
  } catch (error) {
    console.warn('Failed to load security configuration, using defaults.', error)
  }
}

async function refreshTelemetry() {
  try {
    const snapshot = await control.fetchRoboHATStatus()
    const source = (snapshot?.telemetry_source as ControlTelemetry['telemetry_source']) ?? telemetry.value.telemetry_source ?? 'unknown'

    if (source === 'hardware') {
      telemetry.value = {
        ...telemetry.value,
        ...snapshot,
        telemetry_source: 'hardware'
      }
      if (snapshot?.velocity?.linear?.x !== undefined && snapshot.velocity.linear.x !== null) {
        currentSpeed.value = Math.abs(Number(snapshot.velocity.linear.x))
      }
      const cameraSnapshot = snapshot?.camera as Partial<CameraStatusSummary> & { last_frame?: string | null } | undefined
      if (cameraSnapshot) {
        cameraInfo.active = Boolean(cameraSnapshot.active)
        cameraInfo.mode = cameraSnapshot.mode ?? cameraInfo.mode
        cameraInfo.fps = cameraSnapshot.fps ?? cameraInfo.fps
        cameraInfo.client_count = cameraSnapshot.client_count ?? cameraInfo.client_count
        if (cameraSnapshot.last_frame !== undefined) {
          cameraLastFrame.value = cameraSnapshot.last_frame ?? null
        }
      }
    } else {
      telemetry.value = {
        ...telemetry.value,
        safety_state: snapshot?.safety_state ?? telemetry.value.safety_state,
        telemetry_source: source,
        battery: undefined,
        position: undefined,
        velocity: undefined,
        camera: telemetry.value.camera
      }
      currentSpeed.value = 0
    }

    if (snapshot?.safety_state) {
      systemStatus.value = snapshot.safety_state
    }
  } catch (error) {
    // Non-fatal: keep previous telemetry
  }
}

function ensureSession() {
  if (!session.value) {
    session.value = {
      session_id: `local-${Date.now().toString(36)}`
    }
  }
  return session.value
}

async function authenticateControl() {
  if (!canAuthenticate.value || authenticating.value) return

  authenticating.value = true
  authError.value = ''

  const payload: Record<string, unknown> = {
    method: securityConfig.value.auth_level,
    password: authForm.password || undefined,
    totp_code: authForm.totpCode || undefined
  }

  try {
    const response = await api.post('/api/v2/control/manual-unlock', payload)
    const data = response.data ?? {}
    session.value = {
      session_id: data.session_id || `session-${Date.now().toString(36)}`,
      expires_at: data.expires_at
    }
    updateSessionTimer(data.expires_at)
    isControlUnlocked.value = true
    toast.show('Manual control unlocked', 'success', 2500)
    showStatus('Manual control unlocked', true)
  } catch (error) {
    const axiosError = error as AxiosError
    const status = axiosError.response?.status
    if (status === 404 || status === 501) {
      // Backend fallback not implemented – unlock locally with warning
      session.value = ensureSession()
      updateSessionTimer()
      isControlUnlocked.value = true
      toast.show('Manual control unlocked locally (offline mode)', 'warning', 4000)
      showStatus('Manual control unlocked (local mode)', true)
    } else {
      const message = (axiosError.response?.data as any)?.detail || axiosError.message || 'Authentication failed'
      authError.value = message
      showStatus(message, false)
    }
  } finally {
    authenticating.value = false
  }
}

function lockControl() {
  void stopMovement(true)
  isControlUnlocked.value = false
  joystickRef.value?.reset()
  session.value = null
  sessionTimeRemaining.value = 0
  if (sessionTimer) {
    window.clearInterval(sessionTimer)
    sessionTimer = undefined
  }
  currentSpeed.value = 0
  stopCameraFeed()
}

async function verifyCloudflareAuth() {
  try {
    const response = await api.get('/api/v2/control/manual-unlock/status')
    const data = response.data ?? {}
    if (data?.authorized) {
      session.value = {
        session_id: data.session_id || `session-${Date.now().toString(36)}`,
        expires_at: data.expires_at
      }
      updateSessionTimer(data.expires_at)
      isControlUnlocked.value = true
      showStatus('Cloudflare Access verified', true)
      toast.show('Cloudflare Access verified', 'success', 2500)
    } else {
      showStatus('Cloudflare verification failed', false)
    }
  } catch (error) {
    console.warn('Cloudflare verification failed, falling back to local unlock.', error)
    session.value = ensureSession()
    updateSessionTimer()
    isControlUnlocked.value = true
    showStatus('Cloudflare Access assumed (offline mode)', true)
  }
}

function authenticateWithGoogle() {
  toast.show('Google authentication flow is not configured in this environment.', 'info', 4000)
}

function setPerforming(flag: boolean) {
  performing.value = flag
}

function clearMovementTimer() {
  if (movementRepeatTimer) {
    window.clearTimeout(movementRepeatTimer)
    movementRepeatTimer = undefined
  }
}

function scheduleMovementTick() {
  clearMovementTimer()
  if (!joystickEngaged.value) {
    return
  }
  movementRepeatTimer = window.setTimeout(() => {
    if (!joystickEngaged.value) {
      return
    }
    const vector = { ...activeDriveVector.value }
    queueDriveCommand(vector, currentDriveReason)
    scheduleMovementTick()
  }, MOVEMENT_REPEAT_INTERVAL_MS)
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function buildDrivePayload(vector: { linear: number; angular: number }, reason = JOYSTICK_REASON, durationMs = MOVEMENT_DURATION_MS): DriveCommandPayload {
  const speedLimit = clamp(speedLevel.value / 100, 0, 1)
  return {
    session_id: ensureSession().session_id,
    vector: { ...vector },
    duration_ms: durationMs,
    reason,
    max_speed_limit: speedLimit
  }
}

function queueDriveCommand(vector: { linear: number; angular: number }, reason = JOYSTICK_REASON, durationMs = MOVEMENT_DURATION_MS, options: QueueDriveCommandOptions = {}) {
  if (!isControlUnlocked.value || lockout.value) {
    return driveDispatchPromise ?? Promise.resolve()
  }

  pendingDrivePayload = buildDrivePayload(vector, reason, durationMs)

  const immediate = options.immediate === true
  if (!driveCommandActive || immediate) {
    driveDispatchPromise = dispatchDriveCommands()
  }

  return driveDispatchPromise ?? Promise.resolve()
}

async function dispatchDriveCommands(): Promise<void> {
  if (driveCommandActive) {
    return driveDispatchPromise ?? Promise.resolve()
  }

  driveCommandActive = true
  try {
    while (pendingDrivePayload) {
      const payload = pendingDrivePayload
      pendingDrivePayload = null
      if (!payload) {
        continue
      }
      try {
        await control.submitCommand('drive', payload)
        const linearMag = Math.abs(payload.vector.linear ?? 0)
        const angularMag = Math.abs(payload.vector.angular ?? 0)
        currentSpeed.value = Math.max(linearMag, angularMag)
      } catch (error) {
        showStatus('Failed to send drive command', false)
      }
    }
  } finally {
    driveCommandActive = false
    driveDispatchPromise = null
  }
}

function computeDriveVectorFromJoystick(vector: { x: number; y: number }) {
  const speedFactor = clamp(speedLevel.value / 100, 0, 1)
  const linear = clamp(vector.y * speedFactor, -1, 1)
  const angular = clamp(vector.x * speedFactor, -1, 1)
  return { linear, angular }
}

function handleJoystickChange(vector: { x: number; y: number; magnitude: number; active: boolean }) {
  lastJoystickVector.value = { x: vector.x, y: vector.y }
  if (!isControlUnlocked.value) {
    joystickEngaged.value = false
    activeDriveVector.value = { linear: 0, angular: 0 }
    currentSpeed.value = 0
    return
  }

  const driveVector = computeDriveVectorFromJoystick(vector)
  activeDriveVector.value = driveVector
  const engaged = vector.active && (Math.abs(driveVector.linear) > 0.01 || Math.abs(driveVector.angular) > 0.01)

  if (engaged) {
    joystickEngaged.value = true
    currentDriveReason = JOYSTICK_REASON
    clearMovementTimer()
    queueDriveCommand({ ...driveVector }, currentDriveReason)
    scheduleMovementTick()
  } else if (joystickEngaged.value) {
    joystickEngaged.value = false
    void stopMovement(true)
  } else {
    currentSpeed.value = 0
  }
}

function handleJoystickEnd() {
  if (!joystickEngaged.value) {
    return
  }
  joystickEngaged.value = false
  void stopMovement(true)
}

function handleStopButton() {
  joystickRef.value?.reset()
  lastJoystickVector.value = { x: 0, y: 0 }
  joystickEngaged.value = false
  activeDriveVector.value = { linear: 0, angular: 0 }
  void stopMovement(true)
}

function formatCommandValue(value: number) {
  if (!Number.isFinite(value)) {
    return '0.00'
  }
  return value.toFixed(2)
}

async function stopMovement(sendStopCommand = true) {
  clearMovementTimer()
  joystickEngaged.value = false
  activeDriveVector.value = { linear: 0, angular: 0 }
  if (sendStopCommand && isControlUnlocked.value) {
    await queueDriveCommand({ linear: 0, angular: 0 }, 'manual-stop', 0, { immediate: true })
  }
  currentSpeed.value = 0
}

async function emergencyStop() {
  setPerforming(true)
  try {
    await control.submitCommand('emergency', { session_id: ensureSession().session_id })
    currentSpeed.value = 0
    mowingActive.value = false
    showStatus('Emergency stop activated', true)
  } catch (error) {
    showStatus('Failed to trigger emergency stop', false)
  } finally {
    setPerforming(false)
  }
}

async function toggleMowing() {
  if (!canSubmitBlade.value) return
  setPerforming(true)
  try {
    const action = mowingActive.value ? 'disable' : 'enable'
    const response = await control.submitCommand('blade', {
      session_id: ensureSession().session_id,
      action,
      reason: 'manual-control'
    })
    if (response?.result === 'blocked') {
      showStatus('Blade action blocked by safety system', false)
    } else {
      mowingActive.value = !mowingActive.value
      showStatus(mowingActive.value ? 'Mowing started' : 'Mowing stopped', true)
    }
  } catch (error) {
    showStatus('Failed to toggle mowing', false)
  } finally {
    setPerforming(false)
  }
}

async function returnToBase() {
  showStatus('Return to base command queued (placeholder)', true)
}

async function pauseSystem() {
  showStatus('System paused (placeholder)', true)
}

async function resumeSystem() {
  showStatus('System resume command queued (placeholder)', true)
}

// Reactive updates from store events
watch(lockout, (value) => {
  if (value) {
    lockControl()
    const reason = lockoutReason.value || 'Safety lockout active'
    showStatus(reason, false, 6000)
  }
})

watch(isControlUnlocked, (unlocked) => {
  if (unlocked) {
    startCameraFeed(true).catch(() => {
      /* errors handled inside startCameraFeed */
    })
  } else {
    stopCameraFeed()
    joystickRef.value?.reset()
    lastJoystickVector.value = { x: 0, y: 0 }
    joystickEngaged.value = false
    activeDriveVector.value = { linear: 0, angular: 0 }
  }
})

watch(lastCommandResult, (result) => {
  if (!result) return
  if (result.result === 'blocked' || result.result === 'error') {
    showStatus(result.status_reason || 'Command blocked', false)
  }
})

watch(lastEcho, (payload) => {
  if (!payload) return
  if (payload.telemetry) {
    telemetry.value = {
      ...telemetry.value,
      ...payload.telemetry
    }
  }
  if (payload.system_status) {
    systemStatus.value = payload.system_status
  }
})

watch(speedLevel, () => {
  if (!isControlUnlocked.value) {
    currentSpeed.value = 0
    return
  }
  if (!joystickEngaged.value) {
    currentSpeed.value = 0
    return
  }
  const driveVector = computeDriveVectorFromJoystick(lastJoystickVector.value)
  activeDriveVector.value = driveVector
  currentSpeed.value = Math.abs(driveVector.linear)
  clearMovementTimer()
  queueDriveCommand({ ...driveVector }, JOYSTICK_REASON)
  scheduleMovementTick()
})

let telemetryInterval: number | undefined

onMounted(async () => {
  await loadSecurityConfig()
  await refreshTelemetry()
  telemetryInterval = window.setInterval(refreshTelemetry, 5000)
})

onUnmounted(() => {
  if (telemetryInterval) {
    window.clearInterval(telemetryInterval)
    telemetryInterval = undefined
  }
  if (sessionTimer) {
    window.clearInterval(sessionTimer)
    sessionTimer = undefined
  }
  void stopMovement(true)
  stopCameraFeed()
})
</script>

<style scoped>
.control-view {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
}

.security-gate {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
}

.security-card {
  max-width: 500px;
  width: 100%;
}

.card {
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  margin-bottom: 2rem;
}

.card-header {
  background: var(--primary-dark);
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--primary-light);
  border-radius: 8px 8px 0 0;
}

.card-header h3 {
  margin: 0;
  color: var(--accent-green);
  font-size: 1.25rem;
}

.card-body {
  padding: 1.5rem;
}

.security-info {
  margin-bottom: 2rem;
}

.security-level {
  margin-top: 1rem;
}

.level-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.875rem;
}

.level-password {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
  border: 1px solid #ffc107;
}

.level-totp {
  background: rgba(0, 123, 255, 0.2);
  color: #007bff;
  border: 1px solid #007bff;
}

.level-google {
  background: rgba(220, 53, 69, 0.2);
  color: #dc3545;
  border: 1px solid #dc3545;
}

.level-cloudflare {
  background: rgba(0, 255, 146, 0.2);
  color: var(--accent-green);
  border: 1px solid var(--accent-green);
}

.auth-methods {
  margin-bottom: 2rem;
}

.auth-method {
  margin-bottom: 1.5rem;
}

.form-control {
  width: 100%;
  padding: 0.75rem;
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  color: var(--text-color);
  font-size: 1rem;
}

.form-control:focus {
  outline: none;
  border-color: var(--accent-green);
  box-shadow: 0 0 0 2px rgba(0, 255, 146, 0.2);
}

.totp-input {
  text-align: center;
  font-family: monospace;
  font-size: 1.5rem;
  letter-spacing: 0.5rem;
}

.form-text {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-primary {
  background: var(--accent-green);
  color: var(--primary-dark);
}

.btn-secondary {
  background: var(--primary-light);
  color: var(--text-color);
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-warning {
  background: #ffc107;
  color: #000;
}

.btn-info {
  background: #17a2b8;
  color: white;
}

.btn-google {
  background: #db4437;
  color: white;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-emergency {
  background: #ff0000;
  color: white;
  font-size: 1.25rem;
  padding: 1rem 2rem;
  width: 100%;
  margin-bottom: 2rem;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0.7); }
  70% { box-shadow: 0 0 0 10px rgba(255, 0, 0, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0); }
}

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
}

.control-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--primary-dark);
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 2rem;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}

.status-light {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent-green);
}

.status-indicator.emergency .status-light {
  background: #ff0000;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0.3; }
}

.session-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: var(--text-muted);
}

.movement-layout {
  display: flex;
  gap: 2rem;
  align-items: stretch;
  flex-wrap: wrap;
}

.joystick-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.joystick-component {
  width: 220px;
  height: 220px;
  touch-action: none;
}

.joystick-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.movement-actions {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 200px;
}

.stop-button {
  align-self: flex-start;
  padding: 0.85rem 1.5rem;
}

.movement-readout {
  display: flex;
  gap: 1.5rem;
  font-family: 'Roboto Mono', 'Fira Code', monospace;
  font-size: 1rem;
  color: var(--text-muted);
}

.movement-status {
  font-weight: 600;
  color: var(--text-muted);
}

.movement-status.active {
  color: var(--accent-green);
}

.speed-control {
  margin-top: 1rem;
}

.speed-slider {
  width: 100%;
  margin-top: 0.5rem;
}

.mowing-controls, .system-controls {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.camera-feed {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  background: #000;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--primary-light);
}

.camera-feed-error {
  border-color: #ff4343;
}

.camera-frame {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.camera-frame--stream {
  image-rendering: auto;
}

.camera-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--text-muted);
}

.camera-badge {
  position: absolute;
  top: 0.75rem;
  left: 0.75rem;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  padding: 0.3rem 0.75rem;
  border-radius: 4px;
  font-size: 0.75rem;
  letter-spacing: 0.05em;
}

.camera-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 1rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.camera-meta-active {
  color: var(--accent-green);
}

.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.telemetry-item {
  text-align: center;
  padding: 1rem;
  background: var(--primary-dark);
  border-radius: 4px;
}

.telemetry-item label {
  display: block;
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.telemetry-item .value {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-color);
}

.safety-safe {
  color: var(--accent-green);
}

.safety-warning {
  color: #ffc107;
}

.safety-danger {
  color: #ff4343;
}

.info-panel {
  background: var(--primary-dark);
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.alert {
  padding: 1rem;
  border-radius: 4px;
  margin-top: 2rem;
}

.alert-success {
  background: rgba(0, 255, 146, 0.1);
  border: 1px solid var(--accent-green);
  color: var(--accent-green);
}

.alert-danger {
  background: rgba(255, 67, 67, 0.1);
  border: 1px solid #ff4343;
  color: #ff4343;
}

@media (max-width: 768px) {
  .control-status {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }
  
  .movement-layout {
    flex-direction: column;
    align-items: center;
  }
  
  .mowing-controls, .system-controls {
    flex-direction: column;
  }
  
  .telemetry-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
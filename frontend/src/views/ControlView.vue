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
              <label>Confirm Password</label>
              <input 
                v-model="authForm.password"
                type="password" 
                class="form-control"
                placeholder="Enter your password"
                @keyup.enter="authenticateControl"
              >
            </div>

            <!-- TOTP Verification -->
            <div v-else-if="securityConfig.auth_level === 'totp'" class="auth-method">
              <label>Enter TOTP Code</label>
              <input 
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

          <div class="auth-actions">
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

      <!-- Movement Controls -->
      <div class="card">
        <div class="card-header">
          <h3>Movement Controls</h3>
        </div>
        <div class="card-body">
          <div class="movement-grid">
            <!-- Forward -->
            <button 
              class="movement-btn movement-forward"
              :disabled="!canMove"
              @mousedown="startMovement('forward')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
            >
              ⬆️ Forward
            </button>

            <!-- Turn Left -->
            <button 
              class="movement-btn movement-left"
              :disabled="!canMove"
              @mousedown="startMovement('left')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
            >
              ⬅️ Left
            </button>

            <!-- Stop -->
            <button 
              class="movement-btn movement-stop"
              @click="stopMovement"
            >
              🛑 STOP
            </button>

            <!-- Turn Right -->
            <button 
              class="movement-btn movement-right"
              :disabled="!canMove"
              @mousedown="startMovement('right')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
            >
              ➡️ Right
            </button>

            <!-- Backward -->
            <button 
              class="movement-btn movement-backward"
              :disabled="!canMove"
              @mousedown="startMovement('backward')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
            >
              ⬇️ Backward
            </button>
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

            <div class="mowing-height">
              <label>Cutting Height: {{ cuttingHeight }}mm</label>
              <input 
                v-model.number="cuttingHeight"
                type="range" 
                min="20" 
                max="100" 
                step="5"
                class="height-slider"
              >
            </div>
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
              <div class="value">{{ currentSpeed.toFixed(1) }} m/s</div>
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
import type { AxiosError } from 'axios'
import { useControlStore } from '@/stores/control'
import { useApiService } from '@/services/api'
import { useToastStore } from '@/stores/toast'

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
  battery?: { percentage?: number }
  position?: { latitude?: number | null; longitude?: number | null }
  safety_state?: string
  velocity?: { linear?: { x?: number } }
}

const control = useControlStore()
const api = useApiService()
const toast = useToastStore()

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

// UI state
const statusMessage = ref('')
const statusSuccess = ref(false)
const performing = ref(false)
const systemStatus = ref('unknown')
const telemetry = ref<ControlTelemetry>({ safety_state: 'unknown' })
const currentSpeed = ref(0)
const mowingActive = ref(false)
const cuttingHeight = ref(50)
const speedLevel = ref(50)

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

function showStatus(message: string, success: boolean, timeout = 4000) {
  statusMessage.value = message
  statusSuccess.value = success
  if (timeout > 0) {
    window.setTimeout(() => {
      statusMessage.value = ''
    }, timeout)
  }
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
  } catch (error) {
    console.warn('Failed to load security configuration, using defaults.', error)
  }
}

async function refreshTelemetry() {
  try {
    const snapshot = await control.fetchRoboHATStatus()
    telemetry.value = {
      ...telemetry.value,
      ...snapshot
    }
    if (snapshot?.safety_state) {
      systemStatus.value = snapshot.safety_state
    }
    if (snapshot?.velocity?.linear?.x !== undefined && snapshot.velocity.linear.x !== null) {
      currentSpeed.value = Math.abs(Number(snapshot.velocity.linear.x))
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
  isControlUnlocked.value = false
  session.value = null
  sessionTimeRemaining.value = 0
  if (sessionTimer) {
    window.clearInterval(sessionTimer)
    sessionTimer = undefined
  }
  currentSpeed.value = 0
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

async function sendDriveCommand(direction: string) {
  if (!canMove.value) return
  setPerforming(true)
  try {
    const speedFactor = speedLevel.value / 100
    const vector = (() => {
      switch (direction) {
        case 'forward':
          return { linear: speedFactor, angular: 0 }
        case 'backward':
          return { linear: -speedFactor, angular: 0 }
        case 'left':
          return { linear: speedFactor * 0.6, angular: -speedFactor }
        case 'right':
          return { linear: speedFactor * 0.6, angular: speedFactor }
        default:
          return { linear: 0, angular: 0 }
      }
    })()
    await control.submitCommand('drive', {
      session_id: ensureSession().session_id,
      vector,
      duration_ms: 200,
      reason: `manual-${direction}`
    })
    currentSpeed.value = Math.abs(vector.linear ?? 0)
  } catch (error) {
    showStatus('Failed to send drive command', false)
  } finally {
    setPerforming(false)
  }
}

async function startMovement(direction: 'forward' | 'left' | 'right' | 'backward') {
  await sendDriveCommand(direction)
}

async function stopMovement() {
  if (!isControlUnlocked.value) return
  setPerforming(true)
  try {
    await control.submitCommand('drive', {
      session_id: ensureSession().session_id,
      vector: { linear: 0, angular: 0 },
      duration_ms: 0,
      reason: 'manual-stop'
    })
  } catch (error) {
    showStatus('Failed to stop movement', false)
  } finally {
    currentSpeed.value = 0
    setPerforming(false)
  }
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

watch(speedLevel, (value) => {
  if (!isControlUnlocked.value) return
  // Approximate display speed in m/s for the UI
  currentSpeed.value = Number((value / 100 * 1.2).toFixed(2))
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

.movement-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;
  gap: 1rem;
  max-width: 300px;
  margin: 0 auto 2rem;
}

.movement-btn {
  padding: 1rem;
  border: 2px solid var(--primary-light);
  border-radius: 8px;
  background: var(--primary-dark);
  color: var(--text-color);
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
  user-select: none;
}

.movement-forward {
  grid-column: 2;
  grid-row: 1;
}

.movement-left {
  grid-column: 1;
  grid-row: 2;
}

.movement-stop {
  grid-column: 2;
  grid-row: 2;
  background: #ff4343;
  color: white;
}

.movement-right {
  grid-column: 3;
  grid-row: 2;
}

.movement-backward {
  grid-column: 2;
  grid-row: 3;
}

.movement-btn:hover:not(:disabled) {
  border-color: var(--accent-green);
  background: rgba(0, 255, 146, 0.1);
}

.movement-btn:active {
  transform: scale(0.95);
}

.speed-control, .mowing-height {
  margin-top: 1rem;
}

.speed-slider, .height-slider {
  width: 100%;
  margin-top: 0.5rem;
}

.mowing-controls, .system-controls {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
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
  
  .movement-grid {
    max-width: 250px;
  }
  
  .mowing-controls, .system-controls {
    flex-direction: column;
  }
  
  .telemetry-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
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
              />
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
              />
              <small class="form-text text-muted">
                Use your authenticator app (Google Authenticator, Authy, etc.)
              </small>
            </div>

            <!-- Google Auth -->
            <div v-else-if="securityConfig.auth_level === 'google'" class="auth-method">
              <button @click="authenticateWithGoogle" class="btn btn-google">
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
              <button @click="verifyCloudflareAuth" class="btn btn-primary">
                Verify Access
              </button>
            </div>
          </div>

          <div class="auth-actions">
            <button 
              @click="authenticateControl" 
              class="btn btn-primary"
              :disabled="authenticating || !canAuthenticate"
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
          <div class="status-light"></div>
          <span>{{ formatSystemStatus(systemStatus) }}</span>
        </div>
        
        <div class="session-info">
          <small>Control session expires in {{ formatTimeRemaining(sessionTimeRemaining) }}</small>
          <button @click="lockControl" class="btn btn-sm btn-secondary">
            🔒 Lock Control
          </button>
        </div>
      </div>

      <!-- Emergency Stop -->
      <div class="emergency-section">
        <button 
          @click="emergencyStop" 
          class="btn btn-emergency"
          :disabled="performing"
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
              @mousedown="startMovement('forward')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
              class="movement-btn movement-forward"
              :disabled="!canMove"
            >
              ⬆️ Forward
            </button>

            <!-- Turn Left -->
            <button 
              @mousedown="startMovement('left')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
              class="movement-btn movement-left"
              :disabled="!canMove"
            >
              ⬅️ Left
            </button>

            <!-- Stop -->
            <button 
              @click="stopMovement"
              class="movement-btn movement-stop"
            >
              🛑 STOP
            </button>

            <!-- Turn Right -->
            <button 
              @mousedown="startMovement('right')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
              class="movement-btn movement-right"
              :disabled="!canMove"
            >
              ➡️ Right
            </button>

            <!-- Backward -->
            <button 
              @mousedown="startMovement('backward')"
              @mouseup="stopMovement"
              @mouseleave="stopMovement"
              class="movement-btn movement-backward"
              :disabled="!canMove"
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
            />
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
              @click="toggleMowing" 
              class="btn"
              :class="mowingActive ? 'btn-warning' : 'btn-success'"
              :disabled="performing"
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
              />
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
            <button @click="returnToBase" class="btn btn-info" :disabled="performing">
              🏠 Return to Base
            </button>
            
            <button @click="pauseSystem" class="btn btn-warning" :disabled="performing">
              ⏸️ Pause System
            </button>
            
            <button @click="resumeSystem" class="btn btn-success" :disabled="performing">
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApiService } from '@/services/api'
import { useWebSocket } from '@/services/websocket'
import { useAuthStore } from '@/stores/auth'

const api = useApiService()
const { connected, connect, subscribe, unsubscribe } = useWebSocket()
const authStore = useAuthStore()

// State
const isControlUnlocked = ref(false)
const securityConfig = ref({
  auth_level: 'password',
  session_timeout_minutes: 15,
  auto_lock_manual_control: true
})

const authForm = ref({
  password: '',
  totpCode: ''
})

const authenticating = ref(false)
const authError = ref('')
const performing = ref(false)
const statusMessage = ref('')
const statusSuccess = ref(false)

// Control state
const systemStatus = ref('idle')
const mowingActive = ref(false)
const speedLevel = ref(50)
const cuttingHeight = ref(40)
const currentMovement = ref('')
const currentSpeed = ref(0)
const sessionTimeRemaining = ref(900) // 15 minutes in seconds

// Telemetry
const telemetry = ref({
  battery: { percentage: 85.2 },
  position: { latitude: null, longitude: null },
  safety_state: 'safe'
})

// Session management
let sessionTimer: NodeJS.Timeout | null = null
let movementInterval: NodeJS.Timeout | null = null

// Computed
const canAuthenticate = computed(() => {
  switch (securityConfig.value.auth_level) {
    case 'password':
      return authForm.value.password.length > 0
    case 'totp':
      return authForm.value.totpCode.length === 6
    case 'google':
    case 'cloudflare':
      return true
    default:
      return false
  }
})

const canMove = computed(() => {
  return isControlUnlocked.value && systemStatus.value !== 'emergency' && !performing.value
})

// Methods
async function loadSecurityConfig() {
  try {
    const response = await api.get('/api/v2/settings/security')
    securityConfig.value = { ...securityConfig.value, ...response.data }
  } catch (error) {
    console.error('Failed to load security config:', error)
  }
}

async function authenticateControl() {
  if (!canAuthenticate.value) return
  
  authenticating.value = true
  authError.value = ''
  
  try {
    let authData: any = {}
    
    switch (securityConfig.value.auth_level) {
      case 'password':
        authData = { password: authForm.value.password }
        break
      case 'totp':
        authData = { totp_code: authForm.value.totpCode }
        break
      case 'google':
        // Google auth would be handled differently in real implementation
        authData = { google_token: 'mock_token' }
        break
      case 'cloudflare':
        authData = { cloudflare_verified: true }
        break
    }
    
    const response = await api.post('/api/v2/control/authenticate', authData)
    
    if (response.data.authorized) {
      isControlUnlocked.value = true
      startSessionTimer()
      showStatus('Control access granted', true)
    } else {
      authError.value = 'Authentication failed'
    }
  } catch (error: any) {
    authError.value = error.response?.data?.message || 'Authentication failed'
  } finally {
    authenticating.value = false
  }
}

async function authenticateWithGoogle() {
  // Mock implementation - real implementation would use Google OAuth
  authError.value = ''
  authenticating.value = true
  
  try {
    // Simulate Google OAuth flow
    await new Promise(resolve => setTimeout(resolve, 1000))
    isControlUnlocked.value = true
    startSessionTimer()
    showStatus('Google authentication successful', true)
  } catch (error) {
    authError.value = 'Google authentication failed'
  } finally {
    authenticating.value = false
  }
}

async function verifyCloudflareAuth() {
  authenticating.value = true
  authError.value = ''
  
  try {
    const response = await api.get('/api/v2/control/cloudflare-verify')
    if (response.data.verified) {
      isControlUnlocked.value = true
      startSessionTimer()
      showStatus('Cloudflare authentication verified', true)
    } else {
      authError.value = 'Cloudflare authentication not verified'
    }
  } catch (error) {
    authError.value = 'Failed to verify Cloudflare authentication'
  } finally {
    authenticating.value = false
  }
}

function lockControl() {
  isControlUnlocked.value = false
  stopMovement()
  clearSessionTimer()
  authForm.value = { password: '', totpCode: '' }
  showStatus('Control locked', true)
}

function startSessionTimer() {
  clearSessionTimer()
  sessionTimeRemaining.value = securityConfig.value.session_timeout_minutes * 60
  
  sessionTimer = setInterval(() => {
    sessionTimeRemaining.value--
    if (sessionTimeRemaining.value <= 0) {
      lockControl()
      showStatus('Control session expired', false)
    }
  }, 1000)
}

function clearSessionTimer() {
  if (sessionTimer) {
    clearInterval(sessionTimer)
    sessionTimer = null
  }
}

async function emergencyStop() {
  performing.value = true
  try {
    await api.post('/api/v2/control/emergency-stop')
    systemStatus.value = 'emergency'
    stopMovement()
    mowingActive.value = false
    showStatus('Emergency stop activated', true)
  } catch (error) {
    showStatus('Emergency stop failed', false)
  } finally {
    performing.value = false
  }
}

function startMovement(direction: string) {
  if (!canMove.value) return
  
  currentMovement.value = direction
  sendMovementCommand(direction, speedLevel.value)
  
  // Continue sending movement commands while button is held
  movementInterval = setInterval(() => {
    sendMovementCommand(direction, speedLevel.value)
  }, 100)
}

function stopMovement() {
  currentMovement.value = ''
  currentSpeed.value = 0
  
  if (movementInterval) {
    clearInterval(movementInterval)
    movementInterval = null
  }
  
  sendMovementCommand('stop', 0)
}

async function sendMovementCommand(direction: string, speed: number) {
  try {
    await api.post('/api/v2/control/movement', {
      direction,
      speed: speed / 100 // Convert percentage to decimal
    })
  } catch (error) {
    console.error('Movement command failed:', error)
  }
}

async function toggleMowing() {
  performing.value = true
  try {
    if (mowingActive.value) {
      await api.post('/api/v2/control/mowing/stop')
      mowingActive.value = false
      showStatus('Mowing stopped', true)
    } else {
      await api.post('/api/v2/control/mowing/start', {
        cutting_height: cuttingHeight.value
      })
      mowingActive.value = true
      showStatus('Mowing started', true)
    }
  } catch (error) {
    showStatus('Mowing control failed', false)
  } finally {
    performing.value = false
  }
}

async function returnToBase() {
  performing.value = true
  try {
    await api.post('/api/v2/control/return-to-base')
    showStatus('Returning to base', true)
  } catch (error) {
    showStatus('Return to base failed', false)
  } finally {
    performing.value = false
  }
}

async function pauseSystem() {
  performing.value = true
  try {
    await api.post('/api/v2/control/pause')
    systemStatus.value = 'paused'
    showStatus('System paused', true)
  } catch (error) {
    showStatus('Pause failed', false)
  } finally {
    performing.value = false
  }
}

async function resumeSystem() {
  performing.value = true
  try {
    await api.post('/api/v2/control/resume')
    systemStatus.value = 'running'
    showStatus('System resumed', true)
  } catch (error) {
    showStatus('Resume failed', false)
  } finally {
    performing.value = false
  }
}

function formatSecurityLevel(level: string): string {
  const levels = {
    password: 'Password Only',
    totp: 'Password + TOTP',
    google: 'Google Authentication',
    cloudflare: 'Cloudflare Tunnel Auth'
  }
  return levels[level as keyof typeof levels] || level
}

function formatSystemStatus(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function formatTimeRemaining(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}

function showStatus(message: string, success: boolean) {
  statusMessage.value = message
  statusSuccess.value = success
  setTimeout(() => {
    statusMessage.value = ''
  }, 3000)
}

onMounted(async () => {
  await loadSecurityConfig()
  await connect()
  
  // Subscribe to telemetry updates
  subscribe('telemetry.power', (data) => {
    if (data.battery) {
      telemetry.value.battery = data.battery
    }
  })
  
  subscribe('telemetry.navigation', (data) => {
    if (data.position) {
      telemetry.value.position = data.position
    }
  })
  
  subscribe('telemetry.system', (data) => {
    if (data.safety_state) {
      telemetry.value.safety_state = data.safety_state
    }
  })
})

onUnmounted(() => {
  clearSessionTimer()
  if (movementInterval) {
    clearInterval(movementInterval)
  }
  
  unsubscribe('telemetry.power')
  unsubscribe('telemetry.navigation')
  unsubscribe('telemetry.system')
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
<template>
  <div class="control-view">
    <div class="page-header">
      <h1>Manual Control</h1>
      <p class="text-muted">Direct manual operation and emergency controls</p>
    </div>

    <!-- Security Gate -->
    <ControlLockoutGate
      v-if="!isControlUnlocked"
      :auth-level="securityConfig.auth_level"
      :authenticating="authenticating"
      :auth-error="authError"
      :credential="authForm.credential"
      :totp-code="authForm.totpCode"
      :can-authenticate="canAuthenticate"
      @update:credential="authForm.credential = $event"
      @update:totp-code="authForm.totpCode = $event"
      @authenticate="authenticateControl"
      @google-auth="authenticateControl"
      @cloudflare-verify="verifyCloudflareAuth"
    />

    <!-- Main Control Interface (shown when unlocked) -->
    <div v-else class="control-interface">
      <!-- Control Status / Session Bar -->
      <SessionStatusBar
        :system-status="systemStatus"
        :session-time-remaining="sessionTimeRemaining"
        :motor-state="motorControllerState"
        @lock="lockControl"
      />

      <!-- Emergency Stop -->
      <div class="emergency-section">
        <button
          class="btn btn-emergency"
          :disabled="performing"
          @click="emergencyStop"
        >
          🛑 EMERGENCY STOP
        </button>
        <button
          v-if="isEmergencyStopActive"
          class="btn btn-clear-estop"
          :disabled="performing"
          @click="clearEmergencyStop"
        >
          ✅ CLEAR EMERGENCY STOP
        </button>
        <div v-if="isEmergencyStopActive && estopReason" class="estop-reason-banner">
          <span class="estop-reason-label">⚠️ E-Stop reason:</span> {{ estopReason }}
        </div>
      </div>

      <!-- Full-width camera feed with joystick overlay -->
      <div class="camera-with-overlay">
        <CameraPanel
          :camera-info="cameraInfo"
          :camera-display-source="cameraDisplaySource"
          :camera-is-streaming="cameraIsStreaming"
          :camera-stream-unavailable="cameraStreamUnavailable"
          :camera-status-message="cameraStatusMessage"
          :camera-error="cameraError"
          :camera-last-frame="cameraLastFrame"
          :camera-mode-badge="cameraModeBadge"
          @stream-load="handleCameraStreamLoad"
          @stream-error="handleCameraStreamError"
          @retry="retryCameraFeed"
        />

        <!-- Movement Controls overlay -->
        <div class="control-overlay">
          <div class="overlay-top-row">
            <div class="movement-readout-overlay">
              <span>L: {{ formatCommandValue(activeDriveVector.linear) }}</span>
              <span>A: {{ formatCommandValue(activeDriveVector.angular) }}</span>
            </div>
            <div v-if="presetActive" class="movement-status-badge preset">
              ⏳ {{ presetLabel }}
            </div>
            <div v-else-if="joystickEngaged" class="movement-status-badge active">● DRIVING</div>
            <div v-else class="movement-status-badge">○ IDLE</div>
          </div>

          <!-- Preset maneuver buttons -->
          <div class="preset-row">
            <button class="btn-preset" title="Forward ~0.5 m" :disabled="!canMove" @click="runPreset({linear:1,angular:0}, PRESET_NUDGE_MS, 'Forward')">▲</button>
            <button class="btn-preset" title="Turn left 45°"  :disabled="!canMove" @click="runPreset({linear:0,angular:1},  presetTurnMs(45),  '↺ 45°')">↺ 45</button>
            <button class="btn-preset" title="Turn left 90°"  :disabled="!canMove" @click="runPreset({linear:0,angular:1},  presetTurnMs(90),  '↺ 90°')">↺ 90</button>
            <button class="btn-preset" title="Turn 180°"      :disabled="!canMove" @click="runPreset({linear:0,angular:1},  presetTurnMs(180), '↺ 180°')">↕ 180</button>
            <button class="btn-preset" title="Turn right 90°" :disabled="!canMove" @click="runPreset({linear:0,angular:-1}, presetTurnMs(90),  '↻ 90°')">↻ 90</button>
            <button class="btn-preset" title="Turn right 45°" :disabled="!canMove" @click="runPreset({linear:0,angular:-1}, presetTurnMs(45),  '↻ 45°')">↻ 45</button>
            <button class="btn-preset" title="Reverse ~0.5 m" :disabled="!canMove" @click="runPreset({linear:-1,angular:0}, PRESET_NUDGE_MS, 'Reverse')">▼</button>
            <button
              v-if="presetActive"
              class="btn-preset btn-preset--cancel"
              title="Cancel preset"
              @click="cancelPreset"
            >✕</button>
          </div>

          <div class="overlay-joystick-row">
            <VirtualJoystick
              ref="joystickRef"
              class="joystick-component"
              :disabled="!canMove"
              :dead-zone="0.12"
              @change="handleJoystickChange"
              @end="handleJoystickEnd"
            />
            <div class="overlay-side-controls">
              <button
                class="btn btn-danger stop-button"
                :disabled="!isControlUnlocked"
                @click="handleStopButton"
              >
                🛑 Stop
              </button>
              <div class="speed-control-overlay">
                <label>Speed {{ speedLevel }}%</label>
                <input
                  v-model.number="speedLevel"
                  type="range"
                  min="10"
                  max="100"
                  step="10"
                  class="speed-slider"
                  orient="vertical"
                >
              </div>
            </div>
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
    <div v-if="lockout" class="alert" :class="`alert-${lockoutDisplay.severity}`">
      <div class="alert-lockout__header">
        <strong>{{ lockoutDisplay.label }}</strong>
        <span class="alert-lockout__code">{{ lockoutDisplay.code }}</span>
      </div>
      <p class="alert-lockout__reason">{{ lockoutReason }}</p>
      <p>{{ lockoutDisplay.message }}</p>
      <a v-if="remediationLink" class="alert-lockout__link" :href="remediationLink">
        Open remediation steps
      </a>
    </div>
    <div v-if="statusMessage" class="alert" :class="statusSuccess ? 'alert-success' : 'alert-danger'">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { storeToRefs } from 'pinia'
import { useControlStore, type LockoutDisplay, type RoboHATStatus } from '@/stores/control'
import { useApiService } from '@/services/api'
import { useToastStore } from '@/stores/toast'
import { usePreferencesStore } from '@/stores/preferences'
import VirtualJoystick from '@/components/ui/VirtualJoystick.vue'
import CameraPanel from '@/components/control/CameraPanel.vue'
import ControlLockoutGate from '@/components/control/ControlLockoutGate.vue'
import SessionStatusBar from '@/components/control/SessionStatusBar.vue'
import { useCameraFeed } from '@/composables/useCameraFeed'
import { useControlSession } from '@/composables/useControlSession'
import { useJoystickDrive } from '@/composables/useJoystickDrive'

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

interface MotorControllerState {
  ready: boolean
  serialConnected: boolean
  severity: 'success' | 'warning' | 'danger' | 'info'
  label: string
  message: string | null
}

interface JoystickHandle {
  reset: () => void
  setVector: (vector: { x: number; y: number }) => void
}

const control = useControlStore()
const api = useApiService()
const toast = useToastStore()
const preferences = usePreferencesStore()

preferences.ensureInitialized()
const { unitSystem } = storeToRefs(preferences)

// ── Composables ───────────────────────────────────────────────────────────────

const {
  securityConfig, isControlUnlocked, authenticating, authError, authForm,
  session, sessionTimeRemaining, canAuthenticate,
  loadSecurityConfig, restoreExistingControlSession,
  authenticateControl, lockControl: lockControlBase, verifyCloudflareAuth,
  ensureSession,
} = useControlSession()

const {
  cameraInfo, cameraDisplaySource, cameraIsStreaming, cameraStreamUnavailable,
  cameraStatusMessage, cameraError, cameraLastFrame, cameraModeBadge,
  startCameraFeed, stopCameraFeed, retryCameraFeed,
  handleCameraStreamLoad, handleCameraStreamError,
} = useCameraFeed(() => session.value?.session_id ?? null)

// Speed level is ControlView-local (not in preferences store)
const speedLevel = ref(50)

// ── Preset maneuver constants ─────────────────────────────────────────────────
// Fixed 50% speed for all presets so they're consistent regardless of the joystick slider.
const PRESET_SPEED_LIMIT = 0.5
// Degrees per second the mower spins at PRESET_SPEED_LIMIT. Hardware-dependent; adjust if
// turns are consistently over/under. 60°/s is a conservative default for most small mowers.
const PRESET_TURN_DPS = 60
// Duration for a ~0.5 m forward/reverse nudge at PRESET_SPEED_LIMIT.
const PRESET_NUDGE_MS = 1600

function presetTurnMs(degrees: number): number {
  return Math.min(Math.ceil((Math.abs(degrees) / PRESET_TURN_DPS) * 1000), 5000)
}

const {
  joystickEngaged, activeDriveVector,
  handleJoystickChange, handleJoystickEnd, stopMovement,
} = useJoystickDrive({
  isControlUnlocked,
  lockout: computed(() => Boolean(control.lockout)),
  speedLevel: computed(() => speedLevel.value),
  getSessionId: () => session.value?.session_id ?? ensureSession().session_id,
})

// ── Store-backed state ────────────────────────────────────────────────────────

const lockout = computed(() => control.lockout)
const lockoutReason = computed(() => control.lockoutReason)
const remediationLink = computed(() => control.remediationLink)
const lastEcho = computed(() => control.lastEcho)
const lastCommandResult = computed(() => control.lastCommandResult)
const lockoutDisplay = computed<LockoutDisplay>(() => control.lockoutDisplay)

// ── UI state ──────────────────────────────────────────────────────────────────

const statusMessage = ref('')
const statusSuccess = ref(false)
const performing = ref(false)
const systemStatus = ref('unknown')
const telemetry = ref<ControlTelemetry>({ safety_state: 'unknown', telemetry_source: 'unknown' })
const currentSpeed = ref(0)
const mowingActive = ref(false)

const joystickRef = ref<JoystickHandle | null>(null)
const presetActive = ref(false)
const presetLabel = ref('')
let presetCancelFn: (() => void) | null = null

const displaySpeed = computed(() => {
  const value = Number(currentSpeed.value)
  if (!Number.isFinite(value)) return '0.0'
  const converted = unitSystem.value === 'imperial' ? value * 2.23694 : value
  return converted.toFixed(1)
})
const speedUnit = computed(() => (unitSystem.value === 'imperial' ? 'mph' : 'm/s'))

// ── Motor controller state ────────────────────────────────────────────────────

const previousMotorReady = ref<boolean | null>(null)
const previousSerialConnected = ref<boolean | null>(null)

const robohatStatus = computed(() => control.robohatStatus as RoboHATStatus | null)
const motorControllerState = computed<MotorControllerState>(() => describeMotorController(robohatStatus.value))

const isEmergencyStopActive = computed(() => control.emergencyStopActive)
const estopReason = computed(() => control.emergencyStopReason)

const canMove = computed(() =>
  isControlUnlocked.value && !performing.value && !lockout.value && motorControllerState.value.ready && !presetActive.value
)

const canSubmitBlade = computed(() =>
  isControlUnlocked.value && !performing.value && !lockout.value
)

// ── Helpers ───────────────────────────────────────────────────────────────────

function describeMotorError(code: string | null | undefined): string | null {
  if (!code) return null
  switch (code) {
    case 'usb_control_unavailable': return 'Waiting for RoboHAT to hand over USB control. Ensure the RC override is off.'
    case 'pwm_send_failed': return 'Motor PWM command failed to reach the controller. Check USB and power.'
    case 'blade_command_failed': return 'Blade command failed to reach the controller.'
    case 'emergency_stop_failed': return 'Emergency stop command did not acknowledge. Reissue if mower keeps moving.'
    case 'clear_emergency_failed': return 'Emergency clear command did not acknowledge. Verify controller connection.'
    default: return code.replace(/_/g, ' ')
  }
}

function describeMotorController(status: RoboHATStatus | null | undefined): MotorControllerState {
  if (!status) {
    return { ready: false, serialConnected: true, severity: 'info', label: 'Awaiting status', message: 'No RoboHAT telemetry received yet.' }
  }
  const serialConnected = status.serial_connected === undefined ? true : Boolean(status.serial_connected)
  if (!serialConnected) {
    return { ready: false, serialConnected, severity: 'danger', label: 'Disconnected', message: 'Motor controller USB link not detected. Check cabling and power.' }
  }
  const errorMessage = describeMotorError(status.last_error)
  if (status.motor_controller_ok) {
    return { ready: true, serialConnected, severity: 'success', label: 'Ready', message: status.last_watchdog_echo ? `Echo: ${status.last_watchdog_echo}` : null }
  }
  if (errorMessage) {
    const severity = status.last_error === 'usb_control_unavailable' ? 'warning' : 'danger'
    const label = status.last_error === 'usb_control_unavailable' ? 'Handshake pending' : 'Action required'
    return { ready: false, serialConnected, severity, label, message: errorMessage }
  }
  return { ready: false, serialConnected, severity: 'info', label: 'Standby', message: 'Waiting for first motor command acknowledgement.' }
}

function showStatus(message: string, success: boolean, timeout = 4000) {
  statusMessage.value = message
  statusSuccess.value = success
  if (timeout > 0) {
    window.setTimeout(() => { statusMessage.value = '' }, timeout)
  }
}

function getApiErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: string; message?: string } | undefined
    return data?.detail || data?.message || error.message || fallback
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

// ── lockControl with joystick cleanup ─────────────────────────────────────────

function lockControl() {
  void stopMovement(true)
  joystickRef.value?.reset()
  lockControlBase()
  currentSpeed.value = 0
}

// ── Stop button (joystick reset + motor stop) ─────────────────────────────────

function handleStopButton() {
  presetCancelFn?.()
  presetCancelFn = null
  presetActive.value = false
  presetLabel.value = ''
  joystickRef.value?.reset()
  void stopMovement(true)
}

function formatCommandValue(value: number) {
  if (!Number.isFinite(value)) return '0.00'
  return value.toFixed(2)
}

// ── Preset maneuvers ──────────────────────────────────────────────────────────

async function runPreset(vector: { linear: number; angular: number }, durationMs: number, label: string) {
  if (presetActive.value || !isControlUnlocked.value || lockout.value) return
  joystickRef.value?.reset()
  await stopMovement(true)
  presetActive.value = true
  presetLabel.value = label
  let cancelled = false
  let cancelTimer: number | undefined
  presetCancelFn = () => { cancelled = true; if (cancelTimer) window.clearTimeout(cancelTimer) }
  try {
    if (!cancelled) {
      await control.submitCommand('drive', {
        session_id: ensureSession().session_id,
        vector,
        duration_ms: durationMs,
        reason: 'preset-maneuver',
        max_speed_limit: PRESET_SPEED_LIMIT,
      })
    }
    if (!cancelled) {
      await new Promise<void>(resolve => { cancelTimer = window.setTimeout(resolve, durationMs + 150) })
    }
  } catch { /* non-fatal */ } finally {
    presetCancelFn = null
    presetActive.value = false
    presetLabel.value = ''
  }
}

async function cancelPreset() {
  presetCancelFn?.()
  presetCancelFn = null
  presetActive.value = false
  presetLabel.value = ''
  await stopMovement(true)
}

// ── Telemetry ─────────────────────────────────────────────────────────────────

async function refreshTelemetry() {
  try {
    const snapshot = await control.fetchRoboHATStatus()
    const source = (snapshot?.telemetry_source as ControlTelemetry['telemetry_source']) ?? telemetry.value.telemetry_source ?? 'unknown'

    if (source === 'hardware') {
      telemetry.value = { ...telemetry.value, ...snapshot, telemetry_source: 'hardware' }
      if (snapshot?.velocity?.linear?.x !== undefined && snapshot.velocity.linear.x !== null) {
        currentSpeed.value = Math.abs(Number(snapshot.velocity.linear.x))
      }
      const cameraSnapshot = snapshot?.camera as Partial<CameraStatusSummary> & { last_frame?: string | null } | undefined
      if (cameraSnapshot) {
        cameraInfo.value = {
          active: Boolean(cameraSnapshot.active),
          mode: cameraSnapshot.mode ?? cameraInfo.value.mode,
          fps: cameraSnapshot.fps ?? cameraInfo.value.fps,
          client_count: cameraSnapshot.client_count ?? cameraInfo.value.client_count,
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
        camera: telemetry.value.camera,
      }
      currentSpeed.value = 0
    }

    if (snapshot?.safety_state) {
      systemStatus.value = snapshot.safety_state
    }
  } catch {
    // Non-fatal: keep previous telemetry
  }
}

// ── Commands ──────────────────────────────────────────────────────────────────

async function emergencyStop() {
  performing.value = true
  try {
    await control.submitCommand('emergency', { session_id: ensureSession().session_id })
    currentSpeed.value = 0
    mowingActive.value = false
    await control.fetchControlStatus()
    showStatus('Emergency stop activated', true)
  } catch {
    showStatus('Failed to trigger emergency stop', false)
  } finally {
    performing.value = false
  }
}

async function clearEmergencyStop() {
  performing.value = true
  try {
    await control.clearEstop('operator cleared via control panel')
    showStatus('Emergency stop cleared — mower ready', true)
  } catch {
    showStatus('Failed to clear emergency stop', false)
  } finally {
    performing.value = false
  }
}

async function toggleMowing() {
  if (!canSubmitBlade.value) return
  performing.value = true
  try {
    const action = mowingActive.value ? 'disable' : 'enable'
    const response = await control.submitCommand('blade', {
      session_id: ensureSession().session_id,
      action,
      reason: 'manual-control',
    })
    if (response?.result === 'blocked') {
      showStatus('Blade action blocked by safety system', false)
    } else {
      mowingActive.value = !mowingActive.value
      showStatus(mowingActive.value ? 'Mowing started' : 'Mowing stopped', true)
    }
  } catch {
    showStatus('Failed to toggle mowing', false)
  } finally {
    performing.value = false
  }
}

async function returnToBase() {
  performing.value = true
  try {
    await stopMovement(true)
    const response = await api.post('/api/v2/control/return-home', {})
    const status = response.data?.status
    showStatus(status === 'returning_home' ? 'Return-to-base sequence started' : 'Return-to-base command accepted', true)
  } catch (error) {
    showStatus(getApiErrorMessage(error, 'Return-to-base unavailable'), false, 6000)
  } finally {
    performing.value = false
  }
}

async function pauseSystem() {
  performing.value = true
  try {
    await stopMovement(true)
    const response = await api.post('/api/v2/control/pause', {})
    if (response.data?.status === 'paused') systemStatus.value = 'paused'
    showStatus('System paused', true)
  } catch (error) {
    showStatus(getApiErrorMessage(error, 'Failed to pause system'), false, 6000)
  } finally {
    performing.value = false
  }
}

async function resumeSystem() {
  performing.value = true
  try {
    const response = await api.post('/api/v2/control/resume', {})
    if (response.data?.status === 'running') systemStatus.value = 'running'
    showStatus('System resumed', true)
  } catch (error) {
    showStatus(getApiErrorMessage(error, 'Failed to resume system'), false, 6000)
  } finally {
    performing.value = false
  }
}

// ── Watchers ──────────────────────────────────────────────────────────────────

watch(isControlUnlocked, (unlocked) => {
  if (unlocked) {
    startCameraFeed().catch(() => { /* errors handled inside startCameraFeed */ })
  } else {
    stopCameraFeed()
    void stopMovement(true)
  }
})

watch(motorControllerState, (state) => {
  if (previousSerialConnected.value !== null && state.serialConnected !== previousSerialConnected.value) {
    if (!state.serialConnected) {
      toast.show('Motor controller disconnected', 'error', 4000)
      showStatus(state.message || 'Motor controller disconnected', false, 6000)
    } else {
      toast.show('Motor controller connected', 'success', 2500)
      showStatus('Motor controller connected', true, 3000)
    }
  }
  if (previousMotorReady.value !== null && state.ready !== previousMotorReady.value) {
    if (state.ready) {
      toast.show('Motor controller ready', 'success', 2500)
      showStatus('Motor controller ready', true, 2500)
    } else if (state.serialConnected) {
      toast.show(state.message || 'Motor controller not ready', 'warning', 4000)
      if (state.message) showStatus(state.message, false, 6000)
    }
  }
  previousSerialConnected.value = state.serialConnected
  previousMotorReady.value = state.ready
}, { immediate: true })

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
    telemetry.value = { ...telemetry.value, ...payload.telemetry }
  }
  if (payload.system_status) {
    systemStatus.value = payload.system_status
  }
})

// ── Lifecycle ─────────────────────────────────────────────────────────────────

let telemetryInterval: number | undefined
let controlStatusInterval: number | undefined

onMounted(async () => {
  await loadSecurityConfig()
  await restoreExistingControlSession()
  await refreshTelemetry()
  await control.fetchControlStatus()
  telemetryInterval = window.setInterval(refreshTelemetry, 5000)
  controlStatusInterval = window.setInterval(() => control.fetchControlStatus(), 3000)
})

onUnmounted(() => {
  if (telemetryInterval) { window.clearInterval(telemetryInterval); telemetryInterval = undefined }
  if (controlStatusInterval) { window.clearInterval(controlStatusInterval); controlStatusInterval = undefined }
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

.btn-danger {
  background: #dc3545;
  color: white;
}

.btn-emergency {
  background: #ff0000;
  color: white;
  font-size: 1.25rem;
  padding: 1rem 2rem;
  width: 100%;
  margin-bottom: 0.75rem;
  animation: pulse 2s infinite;
}

.btn-clear-estop {
  background: #28a745;
  color: white;
  font-size: 1.1rem;
  padding: 0.875rem 2rem;
  width: 100%;
  margin-bottom: 0.5rem;
  border: 2px solid #1e7e34;
}

.estop-reason-banner {
  background: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 6px;
  color: #856404;
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
  padding: 0.5rem 1rem;
  width: 100%;
}

.estop-reason-label {
  font-weight: 600;
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

.joystick-component {
  width: 220px;
  height: 220px;
  touch-action: none;
}

.stop-button {
  padding: 0.6rem 1rem;
  font-size: 0.9rem;
  white-space: nowrap;
}

/* Full-width camera with controls overlaid */
.camera-with-overlay {
  position: relative;
  margin-bottom: 2rem;
}

.control-overlay {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  background: rgba(10, 10, 10, 0.72);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border: 1px solid rgba(0, 255, 146, 0.25);
  border-radius: 10px;
  padding: 0.75rem;
  z-index: 10;
  /* prevent overlay from triggering camera stream error events */
  pointer-events: auto;
}

.overlay-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.movement-readout-overlay {
  display: flex;
  gap: 0.75rem;
  font-family: 'Roboto Mono', 'Fira Code', monospace;
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.75);
}

.movement-status-badge {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.45);
}

.movement-status-badge.active {
  color: var(--accent-green);
}

.movement-status-badge.preset {
  color: #ffc107;
}

/* Preset maneuver button row */
.preset-row {
  display: flex;
  gap: 0.3rem;
  flex-wrap: wrap;
  justify-content: center;
  padding: 0.25rem 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.btn-preset {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 5px;
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  min-width: 42px;
  padding: 0.3rem 0.4rem;
  transition: background 0.15s, border-color 0.15s;
  white-space: nowrap;
}

.btn-preset:hover:not(:disabled) {
  background: rgba(0, 255, 146, 0.18);
  border-color: var(--accent-green);
  color: var(--accent-green);
}

.btn-preset:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.btn-preset--cancel {
  background: rgba(220, 53, 69, 0.25);
  border-color: #dc3545;
  color: #ff6b6b;
}

.btn-preset--cancel:hover:not(:disabled) {
  background: rgba(220, 53, 69, 0.45);
  border-color: #ff4343;
  color: #fff;
}

.overlay-joystick-row {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.overlay-side-controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.speed-control-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.speed-control-overlay label {
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.65);
  white-space: nowrap;
}

.speed-control-overlay .speed-slider {
  writing-mode: vertical-lr;
  direction: rtl;
  width: 28px;
  height: 120px;
  cursor: pointer;
}

@media (max-width: 768px) {
  .control-overlay {
    bottom: 0.5rem;
    right: 0.5rem;
    padding: 0.5rem;
  }

  .joystick-component {
    width: 160px;
    height: 160px;
  }

  .speed-control-overlay .speed-slider {
    height: 90px;
  }
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

.alert-warning {
  background: rgba(246, 199, 95, 0.12);
  border: 1px solid #f6c75f;
  color: #f6c75f;
}

.alert-info {
  background: rgba(123, 196, 255, 0.12);
  border: 1px solid #7bc4ff;
  color: #7bc4ff;
}

.alert-lockout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.alert-lockout__code {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  opacity: 0.85;
}

.alert-lockout__reason {
  margin-bottom: 0.4rem;
  font-weight: 600;
}

.alert-lockout__link {
  color: inherit;
  font-weight: 600;
  text-decoration: underline;
}

@media (max-width: 768px) {
  .mowing-controls, .system-controls {
    flex-direction: column;
  }

  .telemetry-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>

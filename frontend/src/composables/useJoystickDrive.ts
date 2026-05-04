import { ref, onUnmounted, type Ref } from 'vue'
import { useControlStore } from '@/stores/control'

const MOVEMENT_DURATION_MS = 160
const MOVEMENT_REPEAT_INTERVAL_MS = 120
const JOYSTICK_REASON = 'manual-joystick'

export interface DriveVector { linear: number; angular: number }

export function useJoystickDrive(opts: {
  isControlUnlocked: Ref<boolean>
  lockout: Ref<boolean>
  speedLevel: Ref<number>
  getSessionId: () => string
}) {
  const { isControlUnlocked, lockout, speedLevel, getSessionId } = opts
  const control = useControlStore()

  const joystickEngaged = ref(false)
  const activeDriveVector = ref<DriveVector>({ linear: 0, angular: 0 })
  const lastJoystickVector = ref({ x: 0, y: 0 })

  let movementRepeatTimer: number | undefined
  let currentDriveReason = JOYSTICK_REASON
  let driveDispatchPromise: Promise<void> | null = null
  let driveCommandActive = false
  let pendingDrivePayload: Record<string, unknown> | null = null

  function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value))
  }

  function buildDrivePayload(vector: DriveVector, reason = JOYSTICK_REASON, durationMs = MOVEMENT_DURATION_MS) {
    const speedLimit = clamp(speedLevel.value / 100, 0, 1)
    return { session_id: getSessionId(), vector: { ...vector }, duration_ms: durationMs, reason, max_speed_limit: speedLimit }
  }

  async function dispatchDriveCommands(): Promise<void> {
    if (driveCommandActive) return driveDispatchPromise ?? Promise.resolve()
    driveCommandActive = true
    try {
      while (pendingDrivePayload) {
        const payload = pendingDrivePayload
        pendingDrivePayload = null
        try {
          await control.submitCommand('drive', payload)
        } catch { /* non-fatal */ }
      }
    } finally {
      driveCommandActive = false
      driveDispatchPromise = null
    }
  }

  function queueDriveCommand(vector: DriveVector, reason = JOYSTICK_REASON, durationMs = MOVEMENT_DURATION_MS, cmdOpts: { immediate?: boolean } = {}) {
    if (!isControlUnlocked.value || lockout.value) return driveDispatchPromise ?? Promise.resolve()
    pendingDrivePayload = buildDrivePayload(vector, reason, durationMs)
    if (!driveCommandActive || cmdOpts.immediate) driveDispatchPromise = dispatchDriveCommands()
    return driveDispatchPromise ?? Promise.resolve()
  }

  function clearMovementTimer() {
    if (movementRepeatTimer) { window.clearTimeout(movementRepeatTimer); movementRepeatTimer = undefined }
  }

  function scheduleMovementTick() {
    clearMovementTimer()
    if (!joystickEngaged.value) return
    movementRepeatTimer = window.setTimeout(() => {
      if (!joystickEngaged.value) return
      queueDriveCommand({ ...activeDriveVector.value }, currentDriveReason)
      scheduleMovementTick()
    }, MOVEMENT_REPEAT_INTERVAL_MS)
  }

  function computeDriveVectorFromJoystick(vector: { x: number; y: number }): DriveVector {
    const speedFactor = clamp(speedLevel.value / 100, 0, 1)
    return {
      linear: clamp(vector.y * speedFactor, -1, 1),
      angular: clamp(vector.x * speedFactor, -1, 1),
    }
  }

  function handleJoystickChange(vector: { x: number; y: number; magnitude: number; active: boolean }) {
    lastJoystickVector.value = { x: vector.x, y: vector.y }
    if (!isControlUnlocked.value) {
      joystickEngaged.value = false
      activeDriveVector.value = { linear: 0, angular: 0 }
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
    }
  }

  function handleJoystickEnd() {
    if (!joystickEngaged.value) return
    joystickEngaged.value = false
    void stopMovement(true)
  }

  async function stopMovement(sendStopCommand = true) {
    clearMovementTimer()
    joystickEngaged.value = false
    activeDriveVector.value = { linear: 0, angular: 0 }
    if (sendStopCommand && isControlUnlocked.value) {
      await queueDriveCommand({ linear: 0, angular: 0 }, 'manual-stop', 0, { immediate: true })
    }
  }

  onUnmounted(() => {
    clearMovementTimer()
    pendingDrivePayload = null
  })

  return {
    joystickEngaged, activeDriveVector, lastJoystickVector,
    handleJoystickChange, handleJoystickEnd, stopMovement, queueDriveCommand,
  }
}

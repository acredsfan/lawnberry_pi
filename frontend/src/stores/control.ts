import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import { sendControlCommand, getRoboHATStatus, getControlStatus, clearEmergencyStop as apiClearEmergencyStop } from '../services/api';
import { useWebSocket } from '../services/websocket';

type ControlPayload = Record<string, unknown>;
type ControlEchoPayload = Record<string, unknown>;

export interface ControlCommandResult extends ControlPayload {
  result?: string;
  status?: string;
  command_id?: string;
  status_reason?: string;
  timestamp?: string;
}

export interface RoboHATStatus extends ControlPayload {
  serial_connected?: boolean;
  motor_controller_ok?: boolean;
  last_error?: string | null;
  last_watchdog_echo?: string | null;
  telemetry_source?: string;
  safety_state?: string;
  velocity?: {
    linear?: {
      x?: number | null;
    };
  };
  camera?: {
    active?: boolean;
    mode?: string;
    fps?: number | null;
    client_count?: number | null;
    last_frame?: string | null;
  };
}

export interface LockoutDisplay {
  code: string;
  label: string;
  message: string;
  severity: 'danger' | 'warning' | 'info';
}

interface ControlSocketMessage extends ControlPayload {
  type?: string;
  payload?: ControlEchoPayload;
  active?: boolean;
  reason?: string;
  until?: string | null;
}

function normalizeLockoutReason(reason: unknown): string {
  return String(reason || 'unknown')
    .trim()
    .replace(/[\s-]+/g, '_')
    .toUpperCase();
}

function describeLockoutReason(reason: unknown): LockoutDisplay {
  const code = normalizeLockoutReason(reason);

  switch (code) {
    case 'EMERGENCY_STOP':
    case 'EMERGENCY_STOP_ACTIVE':
    case 'EMERGENCY_STOP_TRIGGERED':
      return {
        code,
        label: 'Emergency stop active',
        message: 'Motion commands stay blocked until the emergency stop is cleared and the mower is safe to resume.',
        severity: 'danger',
      };
    case 'LOW_BATTERY':
    case 'LOW_BATTERY_LOCKOUT':
      return {
        code,
        label: 'Low battery lockout',
        message: 'Drive and blade commands are paused to protect the mower. Recharge or inspect power before resuming.',
        severity: 'warning',
      };
    case 'TILT_SENSOR_LOCKOUT':
      return {
        code,
        label: 'Tilt safety lockout',
        message: 'The mower reported a tilt condition. Stabilize the chassis and verify the area is safe before retrying.',
        severity: 'danger',
      };
    case 'SAFETY_LOCKOUT':
      return {
        code,
        label: 'Safety lockout',
        message: 'A safety interlock is blocking commands. Review the remediation steps before attempting another action.',
        severity: 'warning',
      };
    default:
      return {
        code,
        label: 'Control lockout',
        message: 'Manual control is temporarily blocked. Review controller status and recent safety messages before retrying.',
        severity: 'info',
      };
  }
}

export const useControlStore = defineStore('control', () => {
  function extractRemediationLink(source: ControlPayload | null | undefined): string {
    if (!source) return '';
    return source?.remediation_link || source?.remediation_url || source?.remediation?.docs_link || '';
  }

  function isSafetyLockoutError(error: unknown): boolean {
    const payload = error as {
      message?: string;
      response?: {
        status?: number;
        data?: ControlPayload;
      };
    };
    const status = payload?.response?.status;
    const data = payload?.response?.data;
    const reason = String(data?.status_reason || data?.detail || payload?.message || '').toUpperCase();

    return (
      status === 403 ||
      status === 423 ||
      data?.result === 'blocked' ||
      reason.includes('LOCKOUT') ||
      reason.includes('EMERGENCY_STOP') ||
      reason.includes('EMERGENCY STOP')
    );
  }

  const lockoutActive = ref(false);
  const lockout = ref(false);
  const lockoutReason = ref('');
  const lockoutUntil = ref(null as string | null);
  const lastEcho = ref<ControlEchoPayload | null>(null);
  const lastCommandEcho = ref<ControlEchoPayload | null>(null);
  const lastCommandResult = ref<ControlCommandResult | null>(null);
  const remediationLink = ref('');
  const isLoading = ref(false);
  const commandInProgress = ref(false);
  const robohatStatus = ref<RoboHATStatus | null>(null);
  const emergencyStopActive = ref(false);
  const emergencyStopReason = ref<string | null>(null);

  let _lockoutClearTimer: ReturnType<typeof setTimeout> | null = null;

  function _scheduleLockoutClear(until: string) {
    if (_lockoutClearTimer !== null) {
      clearTimeout(_lockoutClearTimer);
      _lockoutClearTimer = null;
    }
    const ms = new Date(until).getTime() - Date.now();
    if (ms <= 0) {
      clearLockoutState();
      return;
    }
    _lockoutClearTimer = setTimeout(() => {
      _lockoutClearTimer = null;
      clearLockoutState();
    }, ms);
  }

  function applyLockoutState(source: ControlPayload | null | undefined, reason: string, until?: string | null) {
    lockout.value = true;
    lockoutActive.value = true;
    lockoutReason.value = reason || 'Unknown';
    lockoutUntil.value = until ?? null;
    remediationLink.value = extractRemediationLink(source);
    if (until) {
      _scheduleLockoutClear(until);
    } else if (_lockoutClearTimer !== null) {
      // New permanent lockout cancels any pending auto-clear.
      clearTimeout(_lockoutClearTimer);
      _lockoutClearTimer = null;
    }
  }

  function clearLockoutState() {
    if (_lockoutClearTimer !== null) {
      clearTimeout(_lockoutClearTimer);
      _lockoutClearTimer = null;
    }
    lockout.value = false;
    lockoutActive.value = false;
    lockoutReason.value = '';
    lockoutUntil.value = null;
    remediationLink.value = '';
  }

  function handleControlMessage(msg: ControlSocketMessage) {
    if (msg.type === 'echo' || msg.type === 'command_echo') {
      lastEcho.value = msg.payload || msg;
      lastCommandEcho.value = msg.payload || msg;
    }
    if (msg.type === 'lockout') {
      applyLockoutState(msg, msg.reason || 'Unknown', msg.until ?? null);
    }
    if (msg.type === 'unlock') {
      clearLockoutState();
    }
  }

  const ws = useWebSocket('control', {
    onMessage: (msg: ControlSocketMessage) => {
      handleControlMessage(msg);
    }
  });

  async function submitCommand(command: string, payload: ControlPayload = {}) {
    if (lockoutActive.value) {
      throw new Error(`Control locked out: ${lockoutReason.value}`);
    }

    commandInProgress.value = true;
    isLoading.value = true;
    try {
      const result = await sendControlCommand(command, payload) as ControlCommandResult;
      lastCommandResult.value = result;
      lastCommandEcho.value = result;
      if (result.result === 'blocked') {
        applyLockoutState(result, result.status_reason || 'SAFETY_LOCKOUT', result.until as string | undefined);
      }
      return result;
    } catch (e: unknown) {
      const error = e as {
        message?: string;
        response?: {
          data?: ControlPayload;
        };
      };
      const statusReason = String(
        error?.response?.data?.status_reason ||
        error?.response?.data?.detail ||
        error?.message ||
        'Unknown error'
      );
      lastCommandResult.value = { result: 'error', status_reason: statusReason };

      if (isSafetyLockoutError(e)) {
        const untilStr = String(error?.response?.data?.until ?? '') || null;
        applyLockoutState(error?.response?.data, statusReason, untilStr);
      }

      throw e;
    } finally {
      commandInProgress.value = false;
      isLoading.value = false;
    }
  }

  async function fetchRoboHATStatus() {
    try {
      const result = await getRoboHATStatus() as RoboHATStatus;
      robohatStatus.value = result;
      return result;
    } catch (e) {
      robohatStatus.value = null;
      throw e;
    }
  }

  async function fetchControlStatus() {
    try {
      const result = await getControlStatus() as { emergency_stop_active?: boolean; estop_reason?: string | null };
      emergencyStopActive.value = !!result?.emergency_stop_active;
      emergencyStopReason.value = result?.estop_reason ?? null;
      return result;
    } catch {
      // non-fatal — keep last known state
    }
  }

  async function clearEstop(reason = '') {
    try {
      const result = await apiClearEmergencyStop(reason);
      emergencyStopActive.value = false;
      emergencyStopReason.value = null;
      return result;
    } catch (e) {
      throw e;
    }
  }

  const canSubmitCommand = computed(() => {
    return !lockoutActive.value && !commandInProgress.value;
  });

  const lockoutDisplay = computed<LockoutDisplay>(() => describeLockoutReason(lockoutReason.value));

  const lockoutTimeRemaining = computed(() => {
    if (!lockoutUntil.value) return 0;
    const until = new Date(lockoutUntil.value).getTime();
    const now = Date.now();
    return Math.max(0, until - now);
  });

  let unsubscribeFunction: (() => void) | null = null;

  function initWebSocket() {
    unsubscribeFunction = ws.subscribe ? ws.subscribe('control', (msg: ControlSocketMessage) => {
      handleControlMessage(msg);
    }) : null;
  }

  function cleanup() {
    if (unsubscribeFunction) {
      unsubscribeFunction();
      unsubscribeFunction = null;
    }
  }

  return {
    lockout,
    lockoutActive,
    lockoutReason,
    lockoutUntil,
    lastEcho,
    lastCommandEcho,
    lastCommandResult,
    remediationLink,
    isLoading,
    commandInProgress,
    robohatStatus,
    emergencyStopActive,
    emergencyStopReason,
    canSubmitCommand,
    lockoutDisplay,
    lockoutTimeRemaining,
    submitCommand,
    fetchRoboHATStatus,
    fetchControlStatus,
    clearEstop,
    initWebSocket,
    cleanup
  };
});

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { sendControlCommand, getRoboHATStatus } from '../services/api';
import { useWebSocket } from '../services/websocket';

export const useControlStore = defineStore('control', () => {
  function extractRemediationLink(source: any): string {
    if (!source) return '';
    return source?.remediation_link || source?.remediation_url || source?.remediation?.docs_link || '';
  }

  function isSafetyLockoutError(error: any): boolean {
    const status = error?.response?.status;
    const data = error?.response?.data;
    const reason = String(data?.status_reason || data?.detail || error?.message || '').toUpperCase();

    return (
      status === 403 ||
      status === 423 ||
      data?.result === 'blocked' ||
      reason.includes('LOCKOUT') ||
      reason.includes('EMERGENCY_STOP') ||
      reason.includes('EMERGENCY STOP')
    );
  }

  // State
  const lockoutActive = ref(false);
  const lockout = ref(false);
  const lockoutReason = ref('');
  const lockoutUntil = ref(null as string | null);
  const lastEcho = ref(null as null | Record<string, any>);
  const lastCommandEcho = ref(null as null | Record<string, any>);
  const lastCommandResult = ref(null as null | { result: string; status_reason?: string });
  const remediationLink = ref('');
  const isLoading = ref(false);
  const commandInProgress = ref(false);
  const robohatStatus = ref(null as null | Record<string, any>);

  // WebSocket integration for echo/lockout
  const ws = useWebSocket('control', {
    onMessage: (msg: any) => {
      if (msg.type === 'echo' || msg.type === 'command_echo') {
        lastEcho.value = msg.payload || msg;
        lastCommandEcho.value = msg.payload || msg;
      }
      if (msg.type === 'lockout') {
        lockout.value = true;
        lockoutActive.value = msg.active !== false;
        lockoutReason.value = msg.reason || 'Unknown';
        lockoutUntil.value = msg.until || null;
        remediationLink.value = extractRemediationLink(msg);
      }
      if (msg.type === 'unlock') {
        lockout.value = false;
        lockoutActive.value = false;
        lockoutReason.value = '';
        lockoutUntil.value = null;
        remediationLink.value = '';
      }
    }
  });

  // Actions
  async function submitCommand(command: string, payload: any = {}) {
    if (lockoutActive.value) {
      throw new Error(`Control locked out: ${lockoutReason.value}`);
    }
    
    commandInProgress.value = true;
    isLoading.value = true;
    try {
      const result = await sendControlCommand(command, payload);
      lastCommandResult.value = result;
      lastCommandEcho.value = result;
      if (result.result === 'blocked') {
        lockout.value = true;
        lockoutActive.value = true;
        lockoutReason.value = result.status_reason || 'SAFETY_LOCKOUT';
        remediationLink.value = extractRemediationLink(result);
      }
      return result;
    } catch (e: any) {
      const statusReason = e?.response?.data?.status_reason || e?.response?.data?.detail || e?.message || 'Unknown error';
      lastCommandResult.value = { result: 'error', status_reason: statusReason };

      if (isSafetyLockoutError(e)) {
        lockout.value = true;
        lockoutActive.value = true;
        lockoutReason.value = statusReason;
        remediationLink.value = extractRemediationLink(e?.response?.data || e);
      }

      throw e;
    } finally {
      commandInProgress.value = false;
      isLoading.value = false;
    }
  }

  async function fetchRoboHATStatus() {
    try {
      const result = await getRoboHATStatus();
      robohatStatus.value = result;
      return result;
    } catch (e) {
      robohatStatus.value = null;
      throw e;
    }
  }

  // Computed properties
  const canSubmitCommand = computed(() => {
    return !lockoutActive.value && !commandInProgress.value;
  });

  const lockoutTimeRemaining = computed(() => {
    if (!lockoutUntil.value) return 0;
    const until = new Date(lockoutUntil.value).getTime();
    const now = Date.now();
    return Math.max(0, until - now);
  });

  // WebSocket management functions
  let unsubscribeFunction: (() => void) | null = null;
  
  function initWebSocket() {
    // Subscribe and store the unsubscribe function
    unsubscribeFunction = ws.subscribe ? ws.subscribe('control', (msg: any) => {
      // Handle messages manually for testing
      if (msg.type === 'echo' || msg.type === 'command_echo') {
        lastEcho.value = msg.payload || msg;
        lastCommandEcho.value = msg.payload || msg;
      }
      if (msg.type === 'lockout') {
        lockout.value = true;
        lockoutActive.value = msg.active !== false;
        lockoutReason.value = msg.reason || 'Unknown';
        lockoutUntil.value = msg.until || null;
        remediationLink.value = extractRemediationLink(msg);
      }
      if (msg.type === 'unlock') {
        lockout.value = false;
        lockoutActive.value = false;
        lockoutReason.value = '';
        lockoutUntil.value = null;
        remediationLink.value = '';
      }
    }) : null;
  }

  function cleanup() {
    if (unsubscribeFunction) {
      unsubscribeFunction();
      unsubscribeFunction = null;
    }
  }

  return {
    // State
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
    
    // Computed
    canSubmitCommand,
    lockoutTimeRemaining,
    
    // Actions
    submitCommand,
    fetchRoboHATStatus,
    initWebSocket,
    cleanup
  };
});

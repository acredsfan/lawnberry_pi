import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { sendControlCommand, getRoboHATStatus } from '../services/api';
import { useWebSocket } from '../services/websocket';

export const useControlStore = defineStore('control', () => {
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
        remediationLink.value = msg.remediation_link || '';
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
        remediationLink.value = result.remediation_link || '';
      }
      return result;
    } catch (e: any) {
      lastCommandResult.value = { result: 'error', status_reason: e?.message || 'Unknown error' };
      lockout.value = true;
      lockoutActive.value = true;
      lockoutReason.value = e?.message || 'Unknown error';
      remediationLink.value = e?.remediation_link || '';
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
        remediationLink.value = msg.remediation_link || '';
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

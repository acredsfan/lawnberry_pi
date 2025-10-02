import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { sendControlCommand, getRoboHATStatus } from '../services/api';
import { useWebSocket } from '../services/websocket';

export const useControlStore = defineStore('control', () => {
  // State
  const lockout = ref(false);
  const lockoutReason = ref('');
  const lastEcho = ref(null as null | Record<string, any>);
  const lastCommandResult = ref(null as null | { result: string; status_reason?: string });
  const remediationLink = ref('');
  const isLoading = ref(false);

  // WebSocket integration for echo/lockout
  const ws = useWebSocket('control', {
    onMessage: (msg: any) => {
      if (msg.type === 'echo') {
        lastEcho.value = msg.payload;
      }
      if (msg.type === 'lockout') {
        lockout.value = true;
        lockoutReason.value = msg.reason || 'Unknown';
        remediationLink.value = msg.remediation_link || '';
      }
      if (msg.type === 'unlock') {
        lockout.value = false;
        lockoutReason.value = '';
        remediationLink.value = '';
      }
    }
  });

  // Actions
  async function submitCommand(command: string, payload: any = {}) {
    isLoading.value = true;
    try {
      const result = await sendControlCommand(command, payload);
      lastCommandResult.value = result;
      if (result.result === 'blocked') {
        lockout.value = true;
        lockoutReason.value = result.status_reason || 'SAFETY_LOCKOUT';
        remediationLink.value = result.remediation_link || '';
      }
      return result;
    } catch (e: any) {
      lastCommandResult.value = { result: 'error', status_reason: e?.message || 'Unknown error' };
      lockout.value = true;
      lockoutReason.value = e?.message || 'Unknown error';
      remediationLink.value = e?.remediation_link || '';
      throw e;
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchRoboHATStatus() {
    return await getRoboHATStatus();
  }

  return {
    lockout,
    lockoutReason,
    lastEcho,
    lastCommandResult,
    remediationLink,
    isLoading,
    submitCommand,
    fetchRoboHATStatus
  };
});

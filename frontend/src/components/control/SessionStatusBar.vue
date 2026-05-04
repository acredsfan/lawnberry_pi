<!-- src/components/control/SessionStatusBar.vue -->
<template>
  <div>
    <div class="control-status">
      <div class="status-indicator" :class="systemStatus">
        <div class="status-light" />
        <span>{{ formatSystemStatus(systemStatus) }}</span>
      </div>
      <div class="session-info">
        <small>Control session expires in {{ formatTimeRemaining(sessionTimeRemaining) }}</small>
        <button class="btn btn-sm btn-secondary" @click="$emit('lock')">Lock Control</button>
      </div>
    </div>
    <div class="controller-health">
      <div class="controller-chip" :class="`controller-chip--${motorState.severity}`">
        <span class="controller-chip__label">Motor controller</span>
        <span class="controller-chip__value">{{ motorState.label }}</span>
      </div>
      <p v-if="motorState.message" class="controller-chip__message">{{ motorState.message }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  systemStatus: string
  sessionTimeRemaining: number
  motorState: { severity: string; label: string; message: string | null; ready: boolean; serialConnected: boolean }
}>()

defineEmits<{ (e: 'lock'): void }>()

function formatSystemStatus(status: string) {
  switch (status?.toLowerCase()) {
    case 'nominal': case 'ok': case 'ready': return 'Ready'
    case 'active': case 'running': return 'Active'
    case 'caution': case 'warning': return 'Caution'
    case 'emergency': case 'fault': return 'Emergency Stop'
    default: return 'Unknown'
  }
}

function formatTimeRemaining(seconds: number) {
  const s = Math.floor(seconds)
  if (s <= 0) return 'expired'
  const mins = Math.floor(s / 60)
  const secs = s % 60
  if (mins === 0) return `${secs}s`
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}
</script>

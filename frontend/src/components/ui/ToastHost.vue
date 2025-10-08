<template>
  <div class="toast-host" role="region" aria-label="Notifications">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="t.type || 'info'"
      role="status"
      :aria-live="t.type === 'error' ? 'assertive' : 'polite'"
    >
      <span class="toast-msg">{{ t.message }}</span>
      <button class="toast-close" @click="dismiss(t.id)" aria-label="Dismiss">×</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const { toasts } = storeToRefs(toast)
const dismiss = (id: number) => toast.dismiss(id)
</script>

<style scoped>
.toast-host {
  position: fixed;
  right: 16px;
  bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 3000;
  pointer-events: none;
}
.toast {
  min-width: 280px;
  max-width: 420px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(20,20,20,0.9);
  color: #e0e0e0;
  box-shadow: 0 6px 24px rgba(0,0,0,0.3);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  pointer-events: auto;
  transform: translateY(10px);
  opacity: 0;
  animation: toastIn 220ms ease-out forwards;
}
.toast.success { border-color: rgba(0,255,146,0.5); }
.toast.error { border-color: rgba(255,67,67,0.6); }
.toast.info { border-color: rgba(0,153,255,0.5); }
.toast.warning { border-color: rgba(255,193,7,0.6); }

.toast-msg { flex: 1; }

.toast-close {
  background: transparent;
  border: none;
  color: inherit;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

@keyframes toastIn {
  from { transform: translateY(10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .toast { animation: none; opacity: 1; transform: none; }
}
</style>

<template>
  <div class="toast-host" aria-live="polite" aria-atomic="true">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="t.type"
      role="status"
      @click="dismiss(t.id)"
      tabindex="0"
    >
      <span class="icon">{{ iconFor(t.type) }}</span>
      <span class="msg">{{ t.message }}</span>
      <button class="close" @click.stop="dismiss(t.id)" aria-label="Dismiss">×</button>
    </div>
  </div>
  
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const { toasts } = storeToRefs(toast)
const dismiss = (id: number) => toast.dismiss(id)
const iconFor = (t?: string) => t === 'success' ? '✅' : t === 'error' ? '❌' : t === 'warning' ? '⚠️' : 'ℹ️'
</script>

<style scoped>
.toast-host {
  position: fixed;
  right: 1rem;
  top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  z-index: 2000;
}
.toast {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  backdrop-filter: blur(6px);
  box-shadow: 0 6px 24px rgba(0,0,0,0.2);
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(20,20,20,0.8);
  color: #fff;
  min-width: 280px;
  animation: slideIn .25s ease, fadeOut .3s ease 4s forwards;
}
.toast .icon { filter: drop-shadow(0 0 8px currentColor); }
.toast .msg {
  flex: 1;
  font-weight: 600;
}
.toast .close {
  appearance: none;
  background: transparent;
  color: inherit;
  border: none;
  font-size: 1.1rem;
  cursor: pointer;
}
.toast.success { border-color: rgba(0,255,146,0.6); color: #00ff92; }
.toast.error { border-color: rgba(255,67,67,0.6); color: #ff6b6b; }
.toast.warning { border-color: rgba(255,200,0,0.6); color: #ffd166; }
.toast.info { border-color: rgba(0,200,255,0.6); color: #66d9ff; }

@keyframes slideIn { from { transform: translateY(-10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes fadeOut { to { opacity: 0; transform: translateY(-10px); } }

@media (prefers-reduced-motion: reduce) {
  .toast { animation: none !important; }
}
</style>

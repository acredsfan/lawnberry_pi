<template>
  <div class="retro-card status-card">
    <div class="card-header">
      <h3>◢ SYSTEM STATUS ◣</h3>
      <div class="status-indicator" :class="systemStatusClass" />
    </div>
    <div class="card-content">
      <div class="status-row">
        <span class="status-label">UPTIME:</span>
        <span class="status-value uptime">{{ uptimeDisplay }}</span>
      </div>
      <div class="status-row">
        <span class="status-label">CONNECTION:</span>
        <span class="status-value">N/A</span>
      </div>
      <div class="status-row">
        <span class="status-label">STATUS:</span>
        <span class="status-value" :class="systemStatusClass">{{ data?.status ?? 'N/A' }}</span>
      </div>
      <div class="status-row">
        <span class="status-label">MODE:</span>
        <span class="status-value">{{ data?.mode ?? 'N/A' }}</span>
      </div>
      <div class="status-row">
        <span class="status-label">PROGRESS:</span>
        <span class="status-value">—</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ data: Record<string, unknown> | null }>()

const systemStatusClass = computed(() => {
  const s = String(props.data?.status ?? '').toLowerCase()
  if (s.includes('error') || s.includes('fault') || s.includes('emergency')) return 'error'
  if (s.includes('warn') || s.includes('caution')) return 'warning'
  if (s.includes('ok') || s.includes('ready') || s.includes('idle') || s.includes('mowing') || s.includes('active')) return 'active'
  return ''
})

const uptimeDisplay = computed(() => {
  const secs = props.data?.uptime_seconds
  if (secs == null || !Number.isFinite(Number(secs))) return 'N/A'
  const s = Number(secs)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${h}h ${m}m ${sec}s`
})
</script>

<style scoped>
.status-indicator {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #666;
  box-shadow: 0 0 15px currentColor;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
}

.status-indicator.active { background: #00ff00; color: #00ff00; }
.status-indicator.warning { background: #ffff00; color: #ffff00; }
.status-indicator.error { background: #ff0040; color: #ff0040; }

.status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid rgba(0, 255, 255, 0.2);
}
.status-row:last-child { border-bottom: none; }

.status-label {
  font-weight: 700;
  letter-spacing: 1px;
  color: #ffff00;
  text-shadow: 0 0 5px rgba(255, 255, 0, 0.5);
}

.status-value {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #ccc;
}
.status-value.uptime { color: #00ff00; text-shadow: 0 0 10px rgba(0, 255, 0, 0.7); }
.status-value.active { color: #00ff00; text-shadow: 0 0 10px rgba(0, 255, 0, 0.7); }
.status-value.warning { color: #ffff00; text-shadow: 0 0 10px rgba(255, 255, 0, 0.7); }
.status-value.error { color: #ff0040; text-shadow: 0 0 10px rgba(255, 0, 64, 0.7); }
</style>

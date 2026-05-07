<template>
  <div class="retro-card telemetry-card gps-card">
    <div class="card-header">
      <h4>GPS NAVIGATION</h4>
      <div class="gps-icon">🧭</div>
    </div>
    <div class="card-content gps-content">
      <div class="gps-status-line" data-testid="gps-status">{{ gpsStatus }}</div>
      <div class="gps-grid">
        <div class="gps-metric">
          <span class="metric-label">Latitude</span>
          <span class="metric-value">{{ fmt6(data?.latitude) }}</span>
        </div>
        <div class="gps-metric">
          <span class="metric-label">Longitude</span>
          <span class="metric-value">{{ fmt6(data?.longitude) }}</span>
        </div>
        <div class="gps-metric">
          <span class="metric-label">Accuracy</span>
          <span class="metric-value">{{ fmt(data?.accuracy, 'm') }}</span>
        </div>
        <div class="gps-metric">
          <span class="metric-label">Satellites</span>
          <span class="metric-value">{{ data?.satellites ?? 'N/A' }}</span>
        </div>
        <div class="gps-metric">
          <span class="metric-label">HDOP</span>
          <span class="metric-value">{{ fmt(data?.hdop) }}</span>
        </div>
        <div class="gps-metric">
          <span class="metric-label">RTK</span>
          <span class="metric-value">{{ data?.rtk_status ?? 'N/A' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ data: Record<string, unknown> | null }>()

function fmt(v: number | null | undefined, unit = '') {
  if (v == null || !Number.isFinite(Number(v))) return 'N/A'
  return `${Number(v).toFixed(2)}${unit}`
}

function fmt6(v: number | null | undefined) {
  if (v == null || !Number.isFinite(Number(v))) return '--'
  return Number(v).toFixed(6)
}

const gpsStatus = computed(() => {
  const rtk = String(props.data?.rtk_status ?? '').toLowerCase()
  if (rtk.includes('rtk') || rtk === '4' || rtk === '5') return 'RTK FIX'
  const sats = Number(props.data?.satellites ?? 0)
  if (sats > 0 && props.data?.latitude != null) return 'GPS FIX'
  return 'ACQUIRING…'
})
</script>

<style scoped>
.gps-icon {
  font-size: 1.5rem;
  filter: drop-shadow(0 0 10px currentColor);
}

.gps-card .gps-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.gps-status-line {
  font-size: 1rem;
  font-weight: 700;
  color: #00ff00;
  text-transform: uppercase;
  text-shadow: 0 0 12px rgba(0, 255, 0, 0.7);
}

.gps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
}

.gps-metric {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.9rem;
  letter-spacing: 1px;
}

.gps-metric .metric-label {
  color: rgba(0, 255, 255, 0.7);
  text-transform: uppercase;
}

.gps-metric .metric-value {
  color: #ffff00;
  font-weight: 600;
  font-size: 1.1rem;
}
</style>

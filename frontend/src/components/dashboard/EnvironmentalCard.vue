<template>
  <div class="retro-card telemetry-card environmental-card">
    <div class="card-header">
      <h4>ENVIRONMENT</h4>
      <div class="temp-icon">🌡️</div>
    </div>
    <div class="card-content">
      <div class="env-grid">
        <div class="env-metric">
          <span class="metric-label">Temp</span>
          <span class="metric-value" data-testid="temperature-value">{{ fmt(data?.temperature) }}<span class="unit">°C</span></span>
          <span class="metric-status" :class="tempStatusClass">{{ tempStatus }}</span>
        </div>
        <div class="env-metric">
          <span class="metric-label">Humidity</span>
          <span class="metric-value" data-testid="humidity-value">{{ fmt(data?.humidity) }}<span class="unit">%</span></span>
        </div>
        <div class="env-metric">
          <span class="metric-label">Pressure</span>
          <span class="metric-value" data-testid="pressure-value">{{ fmt(data?.pressure) }}<span class="unit"> hPa</span></span>
        </div>
        <div class="env-metric">
          <span class="metric-label">Altitude</span>
          <span class="metric-value" data-testid="altitude-value">{{ fmt(data?.altitude) }}<span class="unit">m</span></span>
        </div>
      </div>
      <div class="env-source">Source: telemetry</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ data: Record<string, unknown> | null }>()

function fmt(v: number | null | undefined) {
  if (v == null || !Number.isFinite(Number(v))) return 'N/A'
  return Number(v).toFixed(1)
}

const tempStatusClass = computed(() => {
  const t = Number(props.data?.temperature ?? NaN)
  if (Number.isNaN(t)) return 'status-unknown'
  if (t > 35 || t < 0) return 'status-warning'
  return 'status-active'
})

const tempStatus = computed(() => {
  const t = Number(props.data?.temperature ?? NaN)
  if (Number.isNaN(t)) return '---'
  if (t > 35) return 'HOT'
  if (t < 0) return 'COLD'
  return 'NORMAL'
})
</script>

<style scoped>
.temp-icon {
  font-size: 1.5rem;
  filter: drop-shadow(0 0 10px currentColor);
}

.env-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
}

.env-metric .metric-label {
  display: block;
  font-size: 0.8rem;
  letter-spacing: 2px;
  color: #00ffff;
  margin-bottom: 0.25rem;
  text-transform: uppercase;
}

.env-metric .metric-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #ffff00;
}

.env-metric .unit {
  font-size: 1rem;
  color: #00ffff;
}

.env-metric .metric-status {
  font-size: 0.75rem;
  letter-spacing: 1px;
  display: inline-block;
  margin-top: 0.35rem;
  font-weight: 700;
  text-transform: uppercase;
}

.metric-status.status-active { color: #00ff00; text-shadow: 0 0 8px rgba(0, 255, 0, 0.6); }
.metric-status.status-warning { color: #ffff00; text-shadow: 0 0 8px rgba(255, 255, 0, 0.6); }
.metric-status.status-error { color: #ff0040; text-shadow: 0 0 8px rgba(255, 0, 64, 0.6); }
.metric-status.status-unknown { color: #888; }

.env-source {
  margin-top: 1rem;
  font-size: 0.75rem;
  letter-spacing: 2px;
  color: rgba(0, 255, 255, 0.7);
  text-transform: uppercase;
}
</style>

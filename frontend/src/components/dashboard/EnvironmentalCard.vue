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
          <span class="metric-value" data-testid="temperature-value">{{ tempDisplay }}<span class="unit">{{ tempUnit }}</span></span>
          <span class="metric-status" :class="tempStatusClass">{{ tempStatus }}</span>
        </div>
        <div class="env-metric">
          <span class="metric-label">Humidity</span>
          <span class="metric-value" data-testid="humidity-value">{{ fmt(data?.humidity) }}<span class="unit">%</span></span>
        </div>
        <div class="env-metric">
          <span class="metric-label">Pressure</span>
          <span class="metric-value" data-testid="pressure-value">{{ pressureDisplay }}<span class="unit"> {{ pressureUnit }}</span></span>
        </div>
        <div class="env-metric">
          <span class="metric-label">Altitude</span>
          <span class="metric-value" data-testid="altitude-value">{{ altitudeDisplay }}<span class="unit">{{ altitudeUnit }}</span></span>
        </div>
      </div>
      <div class="env-source">Source: telemetry</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { usePreferencesStore } from '@/stores/preferences'

const props = defineProps<{ data: Record<string, unknown> | null }>()

const preferences = usePreferencesStore()
const { unitSystem } = storeToRefs(preferences)

function fmt(v: unknown) {
  if (v == null || !Number.isFinite(Number(v))) return 'N/A'
  return Number(v).toFixed(1)
}

const tempDisplay = computed(() => {
  const t = Number(props.data?.temperature ?? null)
  if (!Number.isFinite(t)) return 'N/A'
  const converted = unitSystem.value === 'imperial' ? t * 9 / 5 + 32 : t
  return converted.toFixed(1)
})

const tempUnit = computed(() => unitSystem.value === 'imperial' ? '°F' : '°C')

const pressureDisplay = computed(() => {
  const p = Number(props.data?.pressure ?? null)
  if (!Number.isFinite(p)) return 'N/A'
  const converted = unitSystem.value === 'imperial' ? p * 0.0295299831 : p
  return converted.toFixed(unitSystem.value === 'imperial' ? 2 : 1)
})

const pressureUnit = computed(() => unitSystem.value === 'imperial' ? 'inHg' : 'hPa')

const altitudeDisplay = computed(() => {
  const a = Number(props.data?.altitude ?? null)
  if (!Number.isFinite(a)) return 'N/A'
  const converted = unitSystem.value === 'imperial' ? a * 3.28084 : a
  return converted.toFixed(1)
})

const altitudeUnit = computed(() => unitSystem.value === 'imperial' ? 'ft' : 'm')

const tempStatusClass = computed(() => {
  const t = Number(props.data?.temperature ?? NaN)
  if (Number.isNaN(t)) return 'status-unknown'
  if (t > 40 || t < 0) return 'status-error'
  if (t > 30) return 'status-warning'
  return 'status-active'
})

const tempStatus = computed(() => {
  const t = Number(props.data?.temperature ?? NaN)
  if (Number.isNaN(t)) return '---'
  if (t > 40) return 'HOT'
  if (t < 0) return 'COLD'
  if (t > 30) return 'WARM'
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

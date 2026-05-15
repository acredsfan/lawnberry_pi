<template>
  <div class="retro-card telemetry-card orientation-card">
    <div class="card-header">
      <h4>ORIENTATION</h4>
      <div class="speed-icon">🧭</div>
    </div>
    <div class="card-content orientation-content">
      <div class="orient-row">
        <span class="metric-label">Speed</span>
        <span class="metric-value" data-testid="speed-value">{{ speedDisplay }}<span class="unit"> {{ speedUnit }}</span></span>
        <span class="speed-trend" :class="speedTrendClass">{{ speedTrendArrow }} {{ Math.abs(speedTrendPct).toFixed(0) }}%</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">Heading (Nav)</span>
        <span class="metric-value">{{ formatHeading(data?.heading) }}</span>
        <span
          v-if="data?.navHeadingSource === 'imu_raw'"
          class="heading-source-tag"
          title="Source: IMU raw (localization alignment pending)"
        >(IMU)</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">IMU Yaw</span>
        <span class="metric-value">{{ formatHeading(data?.yaw) }}</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">GPS COG</span>
        <span class="metric-value">{{ formatHeading(data?.gpsHeading) }}</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">Pitch</span>
        <span class="metric-value">{{ fmtDeg(data?.pitch) }}</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">Roll</span>
        <span class="metric-value">{{ fmtDeg(data?.roll) }}</span>
      </div>
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

const speedDisplay = computed(() => {
  const v = Number(props.data?.speed ?? null)
  if (!Number.isFinite(v)) return '—'
  const converted = unitSystem.value === 'imperial' ? v * 2.23694 : v
  return converted.toFixed(1)
})

const speedUnit = computed(() => unitSystem.value === 'imperial' ? 'mph' : 'm/s')

const speedTrendPct = computed(() => Number(props.data?.speedTrend ?? 0))
const speedTrendClass = computed(() =>
  speedTrendPct.value > 0 ? 'trend-up' : speedTrendPct.value < 0 ? 'trend-down' : 'trend-stable'
)
const speedTrendArrow = computed(() =>
  speedTrendPct.value > 0 ? '▲' : speedTrendPct.value < 0 ? '▼' : '▬'
)

function formatHeading(deg: unknown) {
  const d = Number(deg ?? null)
  if (!Number.isFinite(d)) return '—'
  const norm = ((d % 360) + 360) % 360
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  const dir = dirs[Math.round(norm / 45) % 8]
  return `${norm.toFixed(0)}° ${dir}`
}

function fmtDeg(v: unknown) {
  const n = Number(v ?? null)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(1)}°`
}
</script>

<style scoped>
.speed-icon {
  font-size: 1.5rem;
  filter: drop-shadow(0 0 10px currentColor);
}

.orientation-content {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.orient-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.orient-row .metric-label {
  min-width: 100px;
  font-size: 0.8rem;
  color: rgba(0, 255, 255, 0.7);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.orient-row .metric-value {
  font-size: 1.1rem;
  color: #ffff00;
  font-family: 'Courier New', monospace;
  font-weight: 600;
}

.orient-row .unit {
  font-size: 0.85rem;
  color: rgba(0, 255, 255, 0.7);
}

.speed-trend {
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 1px;
}

.speed-trend.trend-up { color: #00ff00; text-shadow: 0 0 8px rgba(0, 255, 0, 0.7); }
.speed-trend.trend-down { color: #ff0040; text-shadow: 0 0 8px rgba(255, 0, 64, 0.7); }
.speed-trend.trend-stable { color: #ffff00; text-shadow: 0 0 8px rgba(255, 255, 0, 0.7); }

.heading-source-tag {
  font-size: 0.75rem;
  color: rgba(255, 165, 0, 0.85);
  font-family: 'Courier New', monospace;
  letter-spacing: 0.5px;
  cursor: default;
}
</style>

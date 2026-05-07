<template>
  <div class="retro-card power-card">
    <div class="card-header">
      <h4>POWER SYSTEM</h4>
      <div class="power-indicator" :class="batteryIconClass" />
    </div>
    <div class="card-content power-content">
      <div class="battery-panel">
        <div class="battery-shell" :class="batteryBarClass">
          <span class="battery-percentage" data-testid="battery-percentage">{{ batteryLevelDisplay }}</span>
        </div>
        <div class="battery-terminal" />
      </div>
      <div class="power-metrics">
        <div class="metric-line">
          <span class="metric-label">Battery Voltage</span>
          <span class="metric-value" data-testid="battery-voltage">{{ fmt(data?.voltage, 'V') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Battery Current</span>
          <span class="metric-value">{{ fmt(data?.current, 'A') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Battery Power</span>
          <span class="metric-value">{{ fmt(data?.power, 'W') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Battery State</span>
          <span class="metric-value">{{ chargeStateDisplay }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Solar Voltage</span>
          <span class="metric-value">{{ fmt(data?.solarVoltage, 'V') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Solar Current</span>
          <span class="metric-value">{{ fmtAbs(data?.solarCurrent, 'A') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Solar Output</span>
          <span class="metric-value">{{ fmtAbs(data?.solarPower, 'W') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Solar Yield (Today)</span>
          <span class="metric-value">{{ fmtWh(data?.solarYieldTodayWh) }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Battery Consumption (Today)</span>
          <span class="metric-value">{{ fmtWh(data?.batteryConsumedTodayWh) }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Load Current</span>
          <span class="metric-value">{{ fmtAbs(data?.loadCurrent, 'A') }}</span>
        </div>
        <div class="metric-line">
          <span class="metric-label">Load Power</span>
          <span class="metric-value">{{ fmtAbs(data?.loadPower, 'W') }}</span>
        </div>
      </div>
    </div>
    <div class="metric-status solar-status" :class="solarStatusClass">{{ solarStatus }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ data: Record<string, unknown> | null }>()

function fmt(value: unknown, unit = '') {
  const n = Number(value ?? null)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(1)}${unit}`
}

function fmtAbs(value: unknown, unit = '') {
  const n = Number(value ?? null)
  if (!Number.isFinite(n)) return '—'
  return `${Math.abs(n).toFixed(1)}${unit}`
}

function fmtWh(value: unknown) {
  const n = Number(value ?? null)
  if (!Number.isFinite(n)) return '—'
  return `${new Intl.NumberFormat('en-US').format(Math.round(Math.max(0, n)))}Wh`
}

const batteryLevelDisplay = computed(() => {
  const pct = Number(props.data?.percentage ?? null)
  if (!Number.isFinite(pct)) return '—'
  return `${pct.toFixed(0)}%`
})

const batteryBarClass = computed(() => {
  const pct = Number(props.data?.percentage ?? -1)
  if (pct > 50) return 'battery-bar-good'
  if (pct > 20) return 'battery-bar-low'
  if (pct >= 0) return 'battery-bar-critical'
  return ''
})

const batteryIconClass = computed(() => {
  const pct = Number(props.data?.percentage ?? -1)
  if (pct > 50) return 'active'
  if (pct > 20) return 'warning'
  if (pct >= 0) return 'error'
  return ''
})

const chargeStateDisplay = computed(() => {
  const cs = props.data?.chargeState
  if (typeof cs === 'string' && cs.length > 0) return cs.toUpperCase()
  const cur = Number(props.data?.current ?? null)
  if (!Number.isFinite(cur)) return '—'
  return cur > 0.05 ? 'CHARGING' : cur < -0.05 ? 'DISCHARGING' : 'IDLE'
})

const solarStatus = computed(() => {
  const val = Number(props.data?.solarPower ?? null)
  if (!Number.isFinite(val)) return 'SOLAR: —'
  if (val > 150) return 'PEAK OUTPUT'
  if (val > 50) return 'HARVESTING'
  if (val > 5) return 'TRICKLE'
  if (val > 0.5) return 'IDLE'
  return 'DARK'
})

const solarStatusClass = computed(() => {
  switch (solarStatus.value) {
    case 'PEAK OUTPUT':
    case 'HARVESTING':
      return 'status-active'
    case 'TRICKLE':
    case 'IDLE':
      return 'status-warning'
    case 'DARK':
      return 'status-error'
    default:
      return 'status-unknown'
  }
})
</script>

<style scoped>
.power-card .power-content {
  display: flex;
  align-items: stretch;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.battery-panel {
  position: relative;
  width: 160px;
  height: 70px;
  border: 2px solid rgba(0, 255, 255, 0.6);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 20, 40, 0.6);
  box-shadow: inset 0 0 20px rgba(0, 255, 255, 0.2);
}

.battery-shell {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(0, 255, 255, 0.1), rgba(0, 100, 150, 0.3));
}

.battery-shell::after {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 4px;
  background: rgba(0, 255, 255, 0.08);
}

.battery-shell.battery-bar-good {
  background: linear-gradient(135deg, rgba(0, 255, 0, 0.15), rgba(0, 100, 50, 0.3));
}
.battery-shell.battery-bar-low {
  background: linear-gradient(135deg, rgba(255, 255, 0, 0.15), rgba(100, 100, 0, 0.3));
}
.battery-shell.battery-bar-critical {
  background: linear-gradient(135deg, rgba(255, 0, 64, 0.2), rgba(100, 0, 20, 0.3));
  animation: batteryWarning 1s ease-in-out infinite;
}

@keyframes batteryWarning {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.battery-percentage {
  position: relative;
  font-size: 1.8rem;
  font-weight: 700;
  color: #00ffff;
  z-index: 1;
  text-shadow: 0 0 12px rgba(0, 255, 255, 0.7);
}

.battery-terminal {
  position: absolute;
  right: -14px;
  top: 50%;
  transform: translateY(-50%);
  width: 12px;
  height: 24px;
  background: rgba(0, 255, 255, 0.6);
  border-radius: 3px;
  box-shadow: 0 0 12px rgba(0, 255, 255, 0.5);
}

.power-metrics {
  flex: 1;
  min-width: 200px;
  display: grid;
  gap: 0.6rem;
}

.power-metrics .metric-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
  letter-spacing: 1px;
}

.power-metrics .metric-label {
  color: rgba(0, 255, 255, 0.7);
  text-transform: uppercase;
}

.power-metrics .metric-value {
  color: #ffff00;
  font-weight: 600;
  font-size: 1.1rem;
}

.power-indicator {
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

.power-indicator.active { background: #00ff00; color: #00ff00; }
.power-indicator.warning { background: #ffff00; color: #ffff00; }
.power-indicator.error { background: #ff0040; color: #ff0040; }

.metric-status {
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 0.25rem 1.5rem 0.75rem;
}

.solar-status.status-active { color: #00ff00; text-shadow: 0 0 10px rgba(0, 255, 0, 0.7); }
.solar-status.status-warning { color: #ffff00; text-shadow: 0 0 10px rgba(255, 255, 0, 0.7); }
.solar-status.status-error { color: #ff6600; text-shadow: 0 0 10px rgba(255, 102, 0, 0.7); }
.solar-status.status-unknown { color: #888; }
</style>

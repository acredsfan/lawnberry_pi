<template>
  <div class="retro-card telemetry-card orientation-card">
    <div class="card-header">
      <h4>ORIENTATION</h4>
      <div class="speed-icon">🧭</div>
    </div>
    <div class="card-content orientation-content">
      <div class="orient-row">
        <span class="metric-label">Speed</span>
        <span class="metric-value" data-testid="speed-value">{{ fmt(data?.speed) }}<span class="unit"> m/s</span></span>
        <span class="speed-trend trend-stable">▬ 0%</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">Heading (Nav)</span>
        <span class="metric-value">{{ fmtDeg(data?.heading) }}</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">IMU Yaw</span>
        <span class="metric-value">{{ fmtDeg(data?.yaw) }}</span>
      </div>
      <div class="orient-row">
        <span class="metric-label">GPS COG</span>
        <span class="metric-value">N/A</span>
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
defineProps<{ data: Record<string, unknown> | null }>()

function fmt(v: number | null | undefined) {
  if (v == null || !Number.isFinite(Number(v))) return 'N/A'
  return Number(v).toFixed(2)
}

function fmtDeg(v: number | null | undefined) {
  if (v == null || !Number.isFinite(Number(v))) return 'N/A'
  return `${Number(v).toFixed(1)}°`
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
  gap: 4px;
}

.orient-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.orient-row .metric-label {
  min-width: 90px;
  font-size: 0.7rem;
  color: #00ff88;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.orient-row .metric-value {
  font-size: 0.85rem;
  color: #00ffff;
  font-family: 'Courier New', monospace;
}

.orient-row .unit {
  font-size: 0.75rem;
  color: #ffff00;
}

.speed-trend {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 1px;
}

.speed-trend.trend-up { color: #00ff00; text-shadow: 0 0 10px rgba(0, 255, 0, 0.7); }
.speed-trend.trend-down { color: #ff0040; text-shadow: 0 0 10px rgba(255, 0, 64, 0.7); }
.speed-trend.trend-stable { color: #ffff00; text-shadow: 0 0 10px rgba(255, 255, 0, 0.7); }
</style>

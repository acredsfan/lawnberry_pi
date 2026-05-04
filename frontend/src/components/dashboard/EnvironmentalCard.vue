<template>
  <div class="card">
    <div class="card-header"><h3>Environmental</h3></div>
    <div class="card-body telemetry-grid">
      <div class="telemetry-item"><label>Temperature</label><div class="value">{{ fmt(data?.temperature, '°C') }}</div></div>
      <div class="telemetry-item"><label>Humidity</label><div class="value">{{ fmt(data?.humidity, '%') }}</div></div>
      <div class="telemetry-item"><label>Pressure</label><div class="value">{{ fmt(data?.pressure, ' hPa') }}</div></div>
      <div class="telemetry-item"><label>Altitude</label><div class="value">{{ fmt(data?.altitude, 'm') }}</div></div>
    </div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ data: Record<string, unknown> | null }>()
function fmt(v: number | null | undefined, unit = '') {
  if (v == null || !Number.isFinite(v)) return 'N/A'
  return `${(v as number).toFixed(1)}${unit}`
}
</script>

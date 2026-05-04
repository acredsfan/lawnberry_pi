<template>
  <div class="card">
    <div class="card-header"><h3>Orientation</h3></div>
    <div class="card-body telemetry-grid">
      <div class="telemetry-item"><label>Speed</label><div class="value">{{ fmt(data?.speed, ' m/s') }}</div></div>
      <div class="telemetry-item"><label>Heading</label><div class="value">{{ fmt(data?.heading, '°') }}</div></div>
      <div class="telemetry-item"><label>Yaw</label><div class="value">{{ fmt(data?.yaw, '°') }}</div></div>
      <div class="telemetry-item"><label>Pitch</label><div class="value">{{ fmt(data?.pitch, '°') }}</div></div>
      <div class="telemetry-item"><label>Roll</label><div class="value">{{ fmt(data?.roll, '°') }}</div></div>
    </div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ data: Record<string, unknown> | null }>()
function fmt(v: number | null | undefined, unit = '') {
  if (v == null || !Number.isFinite(v)) return 'N/A'
  return `${(v as number).toFixed(2)}${unit}`
}
</script>

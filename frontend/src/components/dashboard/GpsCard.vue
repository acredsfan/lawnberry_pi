<template>
  <div class="card">
    <div class="card-header"><h3>GPS Navigation</h3></div>
    <div class="card-body telemetry-grid">
      <div class="telemetry-item"><label>Latitude</label><div class="value">{{ fmt6(data?.latitude) }}</div></div>
      <div class="telemetry-item"><label>Longitude</label><div class="value">{{ fmt6(data?.longitude) }}</div></div>
      <div class="telemetry-item"><label>Accuracy</label><div class="value">{{ fmt(data?.accuracy, 'm') }}</div></div>
      <div class="telemetry-item"><label>Satellites</label><div class="value">{{ data?.satellites ?? 'N/A' }}</div></div>
      <div class="telemetry-item"><label>HDOP</label><div class="value">{{ fmt(data?.hdop) }}</div></div>
      <div class="telemetry-item"><label>RTK</label><div class="value">{{ data?.rtk_status ?? 'N/A' }}</div></div>
    </div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ data: Record<string, unknown> | null }>()
function fmt(v: number | null | undefined, unit = '') {
  if (v == null || !Number.isFinite(v)) return 'N/A'
  return `${(v as number).toFixed(2)}${unit}`
}
function fmt6(v: number | null | undefined, unit = '') {
  if (v == null || !Number.isFinite(v)) return 'N/A'
  return `${(v as number).toFixed(6)}${unit}`
}
</script>

<template>
  <div class="retro-card telemetry-card">
    <div class="card-header"><h3>Power System</h3></div>
    <div class="card-content telemetry-grid">
      <div class="telemetry-item"><label>Battery</label><div class="value">{{ fmt(data?.percentage, '%') }}</div></div>
      <div class="telemetry-item"><label>Voltage</label><div class="value">{{ fmt(data?.voltage, 'V') }}</div></div>
      <div class="telemetry-item"><label>Current</label><div class="value">{{ fmt(data?.current, 'A') }}</div></div>
      <div class="telemetry-item"><label>Power</label><div class="value">{{ fmt(data?.power, 'W') }}</div></div>
      <div class="telemetry-item"><label>Charging</label><div class="value">{{ data?.charging ? 'Yes' : 'No' }}</div></div>
    </div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ data: Record<string, unknown> | null }>()
function fmt(value: number | null | undefined, unit: string) {
  if (value == null || !Number.isFinite(value)) return 'N/A'
  return `${(value as number).toFixed(1)}${unit}`
}
</script>

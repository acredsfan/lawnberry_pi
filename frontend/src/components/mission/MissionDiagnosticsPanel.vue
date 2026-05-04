<!-- frontend/src/components/mission/MissionDiagnosticsPanel.vue -->
<template>
  <div class="mission-diagnostics-panel" v-if="diagnostics">
    <h3 class="panel-title">Run Quality</h3>
    <div class="metric-row">
      <span class="label">Pose quality</span>
      <span class="value" :class="qualityClass">
        {{ diagnostics.average_pose_quality ?? 'unknown' }}
      </span>
    </div>
    <div class="metric-row">
      <span class="label">Pose updates</span>
      <span class="value">{{ diagnostics.pose_update_count }}</span>
    </div>
    <div class="metric-row">
      <span class="label">Heading alignment samples</span>
      <span class="value">{{ diagnostics.heading_alignment_samples }}</span>
    </div>
    <div class="metric-row">
      <span class="label">Blocked commands</span>
      <span class="value" :class="{ 'warn': diagnostics.blocked_command_count > 0 }">
        {{ diagnostics.blocked_command_count }}
      </span>
    </div>
    <div class="run-id">
      <span class="label">Run</span>
      <span class="value mono">{{ diagnostics.run_id.slice(0, 8) }}</span>
    </div>
  </div>
  <div class="mission-diagnostics-panel placeholder" v-else>
    <span class="label">No active run diagnostics</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMissionDiagnostics } from '@/composables/useMissionDiagnostics'

const { diagnostics } = useMissionDiagnostics()

const qualityClass = computed(() => {
  const q = diagnostics.value?.average_pose_quality
  if (!q) return ''
  if (q === 'rtk_fixed') return 'quality-rtk'
  if (q === 'gps_float') return 'quality-ok'
  if (q === 'gps_degraded') return 'quality-warn'
  return 'quality-poor'
})
</script>

<style scoped>
.mission-diagnostics-panel {
  background: var(--color-surface, #1e1e2e);
  border: 1px solid var(--color-border, #313244);
  border-radius: 8px;
  padding: 12px 16px;
  min-width: 220px;
}
.panel-title {
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted, #a6adc8);
  margin: 0 0 10px;
}
.metric-row, .run-id {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 0.875rem;
}
.label { color: var(--color-text-muted, #a6adc8); }
.value { font-weight: 500; color: var(--color-text, #cdd6f4); }
.mono { font-family: monospace; font-size: 0.8rem; }
.warn { color: #fab387; }
.quality-rtk { color: #a6e3a1; }
.quality-ok { color: #89dceb; }
.quality-warn { color: #f9e2af; }
.quality-poor { color: #f38ba8; }
.placeholder { opacity: 0.5; font-size: 0.8rem; }
</style>

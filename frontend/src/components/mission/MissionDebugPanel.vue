<template>
  <div class="debug-panel">
    <button class="panel-header" @click="open = !open" :aria-expanded="open">
      <span class="panel-title">Debug</span>
      <span class="chevron" :class="{ rotated: open }">&#9660;</span>
    </button>

    <div v-show="open" class="panel-body">
      <!-- GPS & Position -->
      <section class="section">
        <div class="section-label">GPS &amp; Position</div>
        <Row label="Accuracy" :value="fmt(navDebug?.gps_accuracy_m, 'm', 3)" :cls="accuracyClass" />
        <Row label="Tier" :value="gpsTierLabel" :cls="accuracyClass" />
        <Row label="Mode" :value="navDebug?.mode ?? '—'" />
      </section>

      <!-- Heading & Path -->
      <section class="section">
        <div class="section-label">Heading &amp; Path</div>
        <Row label="Heading error" :value="fmt(navDebug?.heading_error_deg, '°', 1)" />
        <Row label="Raw heading err" :value="fmt(navDebug?.raw_heading_error_deg, '°', 1)" />
        <Row label="Cross-track err" :value="fmt(navDebug?.cross_track_error_m, 'm', 3)" />
        <Row label="Steer" :value="fmt(navDebug?.steer_deg, '°', 1)" />
        <Row label="Stanley k_cte" :value="navDebug?.stanley_k_cte?.toFixed(2) ?? '—'" />
        <Row label="Stanley dead-band" :value="fmt(navDebug?.stanley_dead_band_m, 'm', 2)" />
        <Row label="Dist to waypoint" :value="fmt(navDebug?.distance_to_waypoint_m, 'm', 2)" />
      </section>

      <!-- Speed & Motors -->
      <section class="section">
        <div class="section-label">Speed &amp; Motors</div>
        <Row label="Base speed" :value="navDebug?.base_speed?.toFixed(3) ?? '—'" />
        <Row label="Left cmd" :value="navDebug?.left_speed_cmd?.toFixed(3) ?? '—'" />
        <Row label="Right cmd" :value="navDebug?.right_speed_cmd?.toFixed(3) ?? '—'" />
        <Row label="Stall boost" :value="navDebug?.stall_boost?.toFixed(2) ?? '—'" />
        <Row label="Traction boost" :value="navDebug?.traction_boost?.toFixed(2) ?? '—'" />
      </section>

      <!-- Encoders -->
      <section class="section">
        <div class="section-label">Encoders</div>
        <Row label="RPM A" :value="navDebug?.enc_rpm_a?.toFixed(1) ?? '—'" />
        <Row label="RPM B" :value="navDebug?.enc_rpm_b?.toFixed(1) ?? '—'" />
        <Row label="Asymmetry" :value="asymmetryLabel" :cls="asymmetryClass" />
      </section>

      <!-- Run Quality -->
      <section class="section">
        <div class="section-label">Run Quality</div>
        <Row label="Pose quality" :value="diagnostics?.average_pose_quality ?? '—'" :cls="qualityClass" />
        <Row label="Pose updates" :value="String(diagnostics?.pose_update_count ?? '—')" />
        <Row label="Align samples" :value="String(diagnostics?.heading_alignment_samples ?? '—')" />
        <Row
          label="Blocked cmds"
          :value="String(diagnostics?.blocked_command_count ?? '—')"
          :cls="(diagnostics?.blocked_command_count ?? 0) > 0 ? 'warn' : ''"
        />
        <Row v-if="diagnostics?.run_id" label="Run ID" :value="diagnostics.run_id.slice(0, 8)" mono />
      </section>

      <div v-if="!navDebug && !diagnostics" class="idle-msg">No active run</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineComponent, h } from 'vue'
import { useNavDebug } from '@/composables/useNavDebug'

const open = ref(false)
const { navDebug, diagnostics } = useNavDebug()

function fmt(val: number | null | undefined, unit: string, decimals: number): string {
  if (val === null || val === undefined) return '—'
  return `${val.toFixed(decimals)} ${unit}`
}

const gpsTierLabel = computed(() => {
  const acc = navDebug.value?.gps_accuracy_m
  if (acc === null || acc === undefined) return 'Degraded'
  if (acc <= 0.05) return 'RTK Fixed'
  if (acc <= 0.25) return 'RTK Float'
  if (acc <= 1.0) return 'Standard'
  return 'Degraded'
})

const accuracyClass = computed(() => {
  const acc = navDebug.value?.gps_accuracy_m
  if (acc === null || acc === undefined) return 'poor'
  if (acc <= 0.05) return 'rtk'
  if (acc <= 0.25) return 'ok'
  if (acc <= 1.0) return 'warn'
  return 'poor'
})

const asymmetryLabel = computed(() => {
  const a = navDebug.value?.enc_rpm_a ?? 0
  const b = navDebug.value?.enc_rpm_b ?? 0
  const min = Math.min(a, b)
  const max = Math.max(a, b)
  if (max < 5 || min === 0) return 'N/A'
  const ratio = max / min
  return ratio >= 1.5 ? `⚠ ${ratio.toFixed(2)}×` : `OK (${ratio.toFixed(2)}×)`
})

const asymmetryClass = computed(() => {
  const a = navDebug.value?.enc_rpm_a ?? 0
  const b = navDebug.value?.enc_rpm_b ?? 0
  const min = Math.min(a, b)
  const max = Math.max(a, b)
  if (max < 5 || min === 0) return ''
  return max / min >= 1.5 ? 'warn' : 'rtk'
})

const qualityClass = computed(() => {
  const q = diagnostics.value?.average_pose_quality
  if (!q) return ''
  if (q === 'rtk_fixed') return 'rtk'
  if (q === 'gps_float') return 'ok'
  if (q === 'gps_degraded') return 'warn'
  return 'poor'
})

// Inline Row component to keep template clean
const Row = defineComponent({
  props: {
    label: String,
    value: String,
    cls: { type: String, default: '' },
    mono: { type: Boolean, default: false },
  },
  setup(props) {
    return () =>
      h('div', { class: 'metric-row' }, [
        h('span', { class: 'label' }, props.label),
        h('span', { class: ['value', props.cls, props.mono ? 'mono' : ''].filter(Boolean) }, props.value),
      ])
  },
})
</script>

<style scoped>
.debug-panel {
  background: var(--color-surface, #1e1e2e);
  border: 1px solid var(--color-border, #313244);
  border-radius: 8px;
  min-width: 240px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 10px 16px;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
}

.panel-title {
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted, #a6adc8);
}

.chevron {
  font-size: 0.7rem;
  color: var(--color-text-muted, #a6adc8);
  transition: transform 0.15s;
}
.chevron.rotated { transform: rotate(180deg); }

.panel-body {
  padding: 0 16px 12px;
}

.section {
  margin-bottom: 10px;
}
.section:last-child { margin-bottom: 0; }

.section-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted, #a6adc8);
  margin-bottom: 4px;
  margin-top: 6px;
  border-bottom: 1px solid var(--color-border, #313244);
  padding-bottom: 2px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
  font-size: 0.82rem;
}

.label { color: var(--color-text-muted, #a6adc8); }
.value { font-weight: 500; color: var(--color-text, #cdd6f4); }
.mono { font-family: monospace; font-size: 0.78rem; }

.rtk  { color: #a6e3a1; }
.ok   { color: #89dceb; }
.warn { color: #fab387; }
.poor { color: #f38ba8; }

.idle-msg {
  text-align: center;
  font-size: 0.8rem;
  color: var(--color-text-muted, #a6adc8);
  opacity: 0.6;
  padding: 8px 0;
}
</style>

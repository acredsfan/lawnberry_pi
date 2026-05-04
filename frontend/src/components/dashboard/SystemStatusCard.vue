<template>
  <div class="card">
    <div class="card-header"><h3>System Status</h3></div>
    <div class="card-body">
      <div class="telemetry-grid">
        <div class="telemetry-item"><label>Status</label><div class="value">{{ data?.status ?? 'N/A' }}</div></div>
        <div class="telemetry-item"><label>Safety</label><div class="value">{{ data?.safety_state ?? 'N/A' }}</div></div>
        <div class="telemetry-item"><label>Mode</label><div class="value">{{ data?.mode ?? 'N/A' }}</div></div>
      </div>
      <div v-if="eventLog.length" class="event-log">
        <h4>Event Log</h4>
        <ul>
          <li v-for="(ev, i) in eventLog.slice(0, 20)" :key="i" class="event-log-item">
            <span class="event-ts">{{ formatTs((ev as Record<string, unknown>).timestamp as string | undefined) }}</span>
            <span>{{ (ev as Record<string, unknown>).message ?? JSON.stringify(ev) }}</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ data: Record<string, unknown> | null; eventLog: Record<string, unknown>[] }>()
function formatTs(ts: string | null | undefined) {
  if (!ts) return ''
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString()
}
</script>

<template>
  <div v-if="missionStore.currentMission" class="mission-status-panel">
    <h2>
      Mission Status:
      <span class="mission-status-pill" :class="`mission-status-pill--${statusTone}`">
        {{ statusLabel }}
      </span>
    </h2>
    <p>Progress: {{ missionStore.progress.toFixed(2) }}%</p>
    <p>Waypoint: {{ waypointProgress }}</p>
    <p v-if="missionStore.statusDetail" class="mission-status-detail">
      {{ missionStore.statusDetail }}
    </p>
    <p v-if="missionStore.isRecoveredPause" class="mission-status-hint">
      Review mower state before resuming — this mission was recovered conservatively after a backend
      restart.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMissionStore, type MissionLifecycleStatus } from '@/stores/mission'

const missionStore = useMissionStore()

const statusLabel = computed(() => {
  switch (missionStore.missionStatus) {
    case 'idle': return 'Idle'
    case 'running': return 'Running'
    case 'paused': return missionStore.isRecoveredPause ? 'Paused (recovered)' : 'Paused'
    case 'completed': return 'Completed'
    case 'aborted': return 'Aborted'
    case 'failed': return 'Failed'
    default: return 'Unknown'
  }
})

const statusTone = computed(() => missionStore.missionStatus as MissionLifecycleStatus || 'idle')

const waypointProgress = computed(() => {
  const total = missionStore.totalWaypoints || missionStore.currentMission?.waypoints.length || 0
  if (!total) return 'No waypoints yet'
  const idx = missionStore.currentWaypointIndex ?? 0
  return `${Math.min(idx + 1, total)} of ${total}`
})
</script>

<style scoped>
.mission-status-panel {
  display: flex; flex-direction: column; gap: 0.5rem;
  padding: 1rem; border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px; background: rgba(255,255,255,0.03);
}
.mission-status-pill {
  display: inline-flex; margin-left: 0.5rem;
  padding: 0.2rem 0.6rem; border-radius: 999px;
  font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.04em;
}
.mission-status-pill--idle,
.mission-status-pill--paused { background: rgba(246,199,95,0.18); color: #f6c75f; }
.mission-status-pill--running,
.mission-status-pill--completed { background: rgba(0,255,146,0.14); color: var(--accent-green); }
.mission-status-pill--aborted,
.mission-status-pill--failed { background: rgba(255,107,107,0.14); color: #ff6b6b; }
.mission-status-detail { color: rgba(255,255,255,0.82); }
.mission-status-hint { color: #f6c75f; font-weight: 600; }
</style>

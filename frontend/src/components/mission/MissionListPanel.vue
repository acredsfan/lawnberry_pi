<template>
  <div class="mission-list-panel">
    <h3 class="panel-title">Saved Missions</h3>
    <p v-if="missionStore.missions.length === 0" class="empty-state">No saved missions.</p>
    <ul v-else class="mission-list">
      <li
        v-for="m in missionStore.missions"
        :key="m.id"
        class="mission-row"
        :class="{ 'mission-row--active': missionStore.currentMission?.id === m.id }"
      >
        <div class="mission-row-info">
          <span class="mission-name">{{ m.name }}</span>
          <span class="mission-meta">{{ m.waypoints.length }} waypoints · {{ formatDate(m.created_at) }}</span>
        </div>
        <div class="mission-row-actions">
          <button class="btn-sm" @click="missionStore.selectMission(m)">Select</button>
          <button
            class="btn-sm"
            :disabled="isDestructiveDisabled(m.id)"
            @click="editMissionName(m)"
          >Edit</button>
          <button
            class="btn-sm btn-sm--danger"
            :disabled="isDestructiveDisabled(m.id)"
            @click="deleteMission(m)"
          >Delete</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useMissionStore, type Mission } from '@/stores/mission'

const missionStore = useMissionStore()

onMounted(() => {
  missionStore.fetchMissions()
})

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

function isDestructiveDisabled(id: string): boolean {
  return (
    missionStore.currentMission?.id === id &&
    (missionStore.missionStatus === 'running' || missionStore.missionStatus === 'paused')
  )
}

async function editMissionName(m: Mission) {
  const newName = prompt('Rename mission:', m.name)
  if (!newName || !newName.trim()) return
  try {
    await missionStore.updateMissionById(m.id, { name: newName.trim() })
  } catch {
    alert('Failed to rename mission.')
  }
}

async function deleteMission(m: Mission) {
  if (!confirm(`Delete mission "${m.name}"?`)) return
  try {
    await missionStore.deleteMissionById(m.id)
  } catch {
    alert('Failed to delete mission.')
  }
}
</script>

<style scoped>
.mission-list-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
  min-width: 260px;
  max-width: 320px;
}
.panel-title {
  margin: 0;
  font-size: 1rem;
  color: #00ffff;
  letter-spacing: 0.04em;
}
.empty-state {
  margin: 0;
  color: rgba(255,255,255,0.45);
  font-size: 0.9rem;
}
.mission-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 400px;
  overflow-y: auto;
}
.mission-row {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.6rem 0.75rem;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.02);
  transition: border-color 0.15s;
}
.mission-row--active {
  border-color: rgba(0,255,255,0.35);
  background: rgba(0,255,255,0.05);
}
.mission-row-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.mission-name {
  font-weight: 600;
  font-size: 0.95rem;
  color: rgba(255,255,255,0.92);
  word-break: break-word;
}
.mission-meta {
  font-size: 0.8rem;
  color: rgba(255,255,255,0.45);
}
.mission-row-actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.btn-sm {
  font-size: 0.8rem;
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.2);
  background: rgba(255,255,255,0.07);
  color: inherit;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-sm:hover:not(:disabled) {
  background: rgba(255,255,255,0.14);
}
.btn-sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-sm--danger {
  border-color: rgba(255,107,107,0.3);
  color: #ff6b6b;
}
.btn-sm--danger:hover:not(:disabled) {
  background: rgba(255,107,107,0.12);
}
</style>

<template>
  <div class="mission-list-panel">
    <div class="panel-header">
      <h3 class="panel-title">Saved Missions</h3>
      <button
        v-if="!missionStore.missionsLoading && !missionStore.missionsError && missionStore.missions.length > 0"
        class="btn-sm btn-sm--danger btn-delete-all"
        :disabled="isAnyMissionActive"
        @click="deleteAll"
      >Delete All</button>
    </div>

    <!-- Loading -->
    <div v-if="missionStore.missionsLoading" class="status-state">
      <span class="spinner" aria-label="Loading missions" />
      <span class="status-text">Loading missions…</span>
    </div>

    <!-- Error -->
    <div v-else-if="missionStore.missionsError" class="status-state status-state--error">
      <span class="status-text">{{ missionStore.missionsError }}</span>
      <button class="btn-sm btn-retry" @click="missionStore.fetchMissions()">Retry</button>
    </div>

    <!-- Empty -->
    <p v-else-if="missionStore.missions.length === 0" class="empty-state">No saved missions.</p>

    <!-- List -->
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
import { computed, onMounted, watch } from 'vue'
import { useMissionStore, type Mission } from '@/stores/mission'
import { useAuthStore } from '@/stores/auth'

const missionStore = useMissionStore()
const authStore = useAuthStore()

const isAnyMissionActive = computed(() =>
  missionStore.missionStatus === 'running' || missionStore.missionStatus === 'paused'
)

onMounted(() => {
  missionStore.fetchMissions()
})

// Re-fetch after login so the list populates without a page reload
watch(
  () => authStore.isAuthenticated,
  (authed) => { if (authed) missionStore.fetchMissions() }
)

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

async function deleteAll() {
  if (!confirm(`Delete all ${missionStore.missions.length} saved missions? This cannot be undone.`)) return
  try {
    await missionStore.deleteAllMissions()
  } catch {
    alert('Failed to delete all missions.')
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
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.panel-title {
  margin: 0;
  font-size: 1rem;
  color: #00ffff;
  letter-spacing: 0.04em;
}
.btn-delete-all {
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  white-space: nowrap;
}
.status-state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}
.status-state--error {
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}
.status-text {
  font-size: 0.875rem;
  color: rgba(255,255,255,0.55);
}
.status-state--error .status-text {
  color: #ff6b6b;
}
.btn-retry {
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  border-color: rgba(0,255,255,0.3);
  color: #00ffff;
}
.btn-retry:hover {
  background: rgba(0,255,255,0.08);
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0,255,255,0.2);
  border-top-color: #00ffff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
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

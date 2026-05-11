<template>
  <div class="mission-controls">
    <input :value="missionName" placeholder="Mission Name" @input="$emit('update:missionName', ($event.target as HTMLInputElement).value)" />
    <button
      :disabled="creatingMission || !missionName || missionStore.waypoints.length === 0"
      @click="$emit('create')"
    >
      {{ creatingMission ? 'Creating...' : 'Create Mission' }}
    </button>
    <button
      v-if="isSavedMission && !isMissionActive"
      :disabled="savingChanges"
      @click="$emit('save')"
    >
      {{ savingChanges ? 'Saving...' : 'Save changes' }}
    </button>
    <button
      :disabled="startingMission || !missionStore.currentMission"
      @click="$emit('start')"
    >
      {{ startingMission ? 'Starting...' : 'Start Mission' }}
    </button>
    <button
      :disabled="missionStore.missionStatus !== 'running'"
      @click="$emit('pause')"
    >
      Pause
    </button>
    <button
      :disabled="missionStore.missionStatus !== 'paused'"
      @click="$emit('resume')"
    >
      Resume
    </button>
    <button :disabled="!missionStore.currentMission" @click="$emit('abort')">
      Abort
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMissionStore } from '@/stores/mission'

const missionStore = useMissionStore()

defineProps<{
  missionName: string
  creatingMission?: boolean
  startingMission?: boolean
  savingChanges?: boolean
}>()

defineEmits<{
  (e: 'create'): void
  (e: 'save'): void
  (e: 'start'): void
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'abort'): void
  (e: 'update:missionName', value: string): void
}>()

const isSavedMission = computed(() =>
  !!missionStore.currentMission &&
  missionStore.missions.some(m => m.id === missionStore.currentMission?.id)
)
const isMissionActive = computed(() =>
  missionStore.missionStatus === 'running' || missionStore.missionStatus === 'paused'
)
</script>

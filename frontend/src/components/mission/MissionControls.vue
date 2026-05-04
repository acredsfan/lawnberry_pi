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
import { useMissionStore } from '@/stores/mission'

const missionStore = useMissionStore()

defineProps<{
  missionName: string
  creatingMission?: boolean
  startingMission?: boolean
}>()

defineEmits<{
  (e: 'create'): void
  (e: 'start'): void
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'abort'): void
  (e: 'update:missionName', value: string): void
}>()
</script>

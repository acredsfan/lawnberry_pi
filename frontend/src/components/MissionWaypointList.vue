<template>
  <div class="waypoint-list">
    <div class="header-row">
      <h2>Waypoints</h2>
      <div class="list-actions" v-if="missionStore.waypoints.length">
        <button class="btn btn-xs" @click="undoLast">Undo last</button>
        <button class="btn btn-xs btn-danger" @click="clearAll">Clear all</button>
      </div>
    </div>
    <Draggable v-model="localWaypoints" item-key="id" @end="onDragEnd">
      <template #item="{ element: waypoint, index }">
        <li class="waypoint-item">
          <span>Waypoint {{ index + 1 }}: ({{ waypoint.lat.toFixed(4) }}, {{ waypoint.lon.toFixed(4) }})</span>
          <div class="waypoint-controls">
            <label>Blade On: <input type="checkbox" v-model="waypoint.blade_on" @change="updateWaypoint(waypoint)"></label>
            <label>Speed: <input type="range" min="0" max="100" v-model.number="waypoint.speed" @change="updateWaypoint(waypoint)"> {{ waypoint.speed }}%</label>
            <button @click="removeWaypoint(waypoint.id)">Remove</button>
          </div>
        </li>
      </template>
    </Draggable>
    <div v-if="missionStore.waypoints.length === 0">
      <p>Click on the map to add waypoints.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useMissionStore } from '@/stores/mission';
import type { Waypoint } from '@/stores/mission';
import { VueDraggableNext as Draggable } from 'vue-draggable-next';

const missionStore = useMissionStore();
const localWaypoints = ref([...missionStore.waypoints]);

watch(() => missionStore.waypoints, (newWaypoints) => {
  localWaypoints.value = [...newWaypoints];
}, { deep: true });

const removeWaypoint = (id: string) => {
  missionStore.removeWaypoint(id);
};

const updateWaypoint = (waypoint: Waypoint) => {
  missionStore.updateWaypoint(waypoint);
};

const onDragEnd = () => {
  missionStore.reorderWaypoints(localWaypoints.value);
};

function clearAll() {
  if (missionStore.waypoints.length && confirm('Clear all waypoints?')) {
    missionStore.clearWaypoints();
  }
}

function undoLast() {
  missionStore.removeLastWaypoint();
}
</script>

<style scoped>
.waypoint-list ul {
  list-style-type: none;
  padding: 0;
}
.waypoint-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  border-bottom: 1px solid #eee;
  cursor: grab;
}
.waypoint-controls {
  display: flex;
  gap: 1rem;
  align-items: center;
}
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: .5rem;
}
.btn { padding: .25rem .5rem; border: 1px solid var(--primary-light); background: var(--primary-dark); color: var(--text-color); border-radius: 4px; cursor: pointer; }
.btn-xs { font-size: .75rem; }
.btn-danger { background: #5a1a1a; border-color: #a33; color: #fff; }
.list-actions { display: flex; gap: .5rem; }
</style>

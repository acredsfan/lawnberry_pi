<template>
  <div class="mission-planner-view">
    <h1>Mission Planner</h1>
    <div ref="mapContainer" class="map-container"></div>
    <MissionWaypointList />
    <div class="mission-controls">
      <input v-model="missionName" placeholder="Mission Name" />
      <button @click="createMission" :disabled="!missionName || missionStore.waypoints.length === 0">Create Mission</button>
      <button @click="startMission" :disabled="!missionStore.currentMission">Start Mission</button>
      <button @click="pauseMission" :disabled="missionStore.missionStatus !== 'running'">Pause</button>
      <button @click="resumeMission" :disabled="missionStore.missionStatus !== 'paused'">Resume</button>
      <button @click="abortMission" :disabled="!missionStore.currentMission">Abort</button>
    </div>
    <div v-if="missionStore.currentMission">
      <h2>Mission Status: {{ missionStore.missionStatus }}</h2>
      <p>Progress: {{ missionStore.progress.toFixed(2) }}%</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import MissionWaypointList from '@/components/MissionWaypointList.vue';
import { useMissionStore } from '@/stores/mission';

const missionStore = useMissionStore();
const mapContainer = ref<HTMLElement | null>(null);
let map: L.Map | null = null;
const missionName = ref('');

onMounted(() => {
  if (mapContainer.value) {
    map = L.map(mapContainer.value).setView([51.505, -0.09], 13); // Default view
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);

    map.on('click', (e: L.LeafletMouseEvent) => {
      missionStore.addWaypoint(e.latlng.lat, e.latlng.lng);
      renderWaypoints();
    });
    
    renderWaypoints();
  }
});

onUnmounted(() => {
  if (map) {
    map.remove();
  }
});

const renderWaypoints = () => {
  if (!map) return;
  // Clear existing markers
  map.eachLayer((layer) => {
    if (layer instanceof L.Marker) {
      map?.removeLayer(layer);
    }
  });

  // Add new markers
  missionStore.waypoints.forEach(wp => {
    L.marker([wp.lat, wp.lon]).addTo(map!);
  });
};

const createMission = () => {
  if (missionName.value) {
    missionStore.createMission(missionName.value);
  }
};

const startMission = () => missionStore.startCurrentMission();
const pauseMission = () => missionStore.pauseCurrentMission();
const resumeMission = () => missionStore.resumeCurrentMission();
const abortMission = () => missionStore.abortCurrentMission();

</script>

<style scoped>
.mission-planner-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.map-container {
  height: 500px;
  width: 100%;
}
.mission-controls {
  display: flex;
  gap: 1rem;
  align-items: center;
}
</style>

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
import { ref, onMounted, onUnmounted, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import MissionWaypointList from '@/components/MissionWaypointList.vue';
import { useMissionStore } from '@/stores/mission';

const missionStore = useMissionStore();
const mapContainer = ref<HTMLElement | null>(null);
let map: L.Map | null = null;
let overlayGroup: L.LayerGroup | null = null;
const missionName = ref('');

onMounted(() => {
  if (mapContainer.value) {
    map = L.map(mapContainer.value, {
      maxZoom: 22, // Allow deeper zoom
    }).setView([51.505, -0.09], 13); // Default view

    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, // Standard OSM max zoom
      attribution: '© OpenStreetMap contributors',
    });

    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 22, // Allow deeper zoom for satellite
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    });

    const baseMaps = {
      "OpenStreetMap": osmLayer,
      "Satellite": satelliteLayer
    };

    satelliteLayer.addTo(map); // Default to satellite view
    L.control.layers(baseMaps).addTo(map);

    overlayGroup = L.layerGroup().addTo(map)

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
  if (!map || !overlayGroup) return;
  overlayGroup.clearLayers();

  // Add markers for each waypoint
  const latlngs: L.LatLngExpression[] = []
  missionStore.waypoints.forEach(wp => {
    const ll: L.LatLngExpression = [wp.lat, wp.lon]
    latlngs.push(ll)
    L.marker(ll).addTo(overlayGroup!)
  })

  // Draw polyline path if 2+ points
  if (latlngs.length >= 2) {
    L.polyline(latlngs, { color: '#00ffff', weight: 3 }).addTo(overlayGroup!)
  }
};

// Re-render when waypoints change (add/remove/reorder)
watch(() => missionStore.waypoints, () => {
  renderWaypoints()
}, { deep: true })

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

<template>
  <div class="mission-planner-view">
    <h1>Mission Planner</h1>
    <div class="map-toolbar">
      <label class="follow-toggle"><input type="checkbox" v-model="followMower" /> Follow mower</label>
      <button class="btn" @click="recenterToMower" :disabled="!mowerLatLng">🎯 Recenter</button>
      <span v-if="providerBadge" class="provider-badge">{{ providerBadge }}</span>
    </div>
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
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import MissionWaypointList from '@/components/MissionWaypointList.vue';
import { useMissionStore } from '@/stores/mission';
import { useMapStore } from '@/stores/map';
import { useApiService } from '@/services/api';
import { useWebSocket } from '@/services/websocket';
import { getOsmTileLayer, shouldUseGoogleProvider } from '@/utils/mapProviders';

const missionStore = useMissionStore();
const mapStore = useMapStore();
const api = useApiService();
const telemetrySocket = useWebSocket('telemetry');
const mapContainer = ref<HTMLElement | null>(null);
let map: L.Map | null = null;
let overlayGroup: L.LayerGroup | null = null;
let baseTileLayer: L.Layer | null = null;
let googleLayer: any = null;
let googleHandlers: Record<string, any> = {};
const followMower = ref(true);
const mowerLatLng = ref<[number, number] | null>(null);
const gpsAccuracyMeters = ref<number | null>(null);
let accuracyCircle: L.Polygon | null = null;
const providerBadge = ref('');
const missionName = ref('');
const mapReady = ref(false);
let pendingCenter: { lat: number; lon: number; minZoom: number } | null = null;
let pendingCenterTimer: number | null = null;
let navigationHandler: ((payload: any) => void) | null = null;
let mapReadyHandler: (() => void) | null = null;
let componentDestroyed = false;

onMounted(async () => {
  componentDestroyed = false;
  if (!mapContainer.value) return;

  // Ensure Leaflet default marker icons resolve under bundler
  try {
    (L.Icon.Default as any).mergeOptions({
      iconRetinaUrl: markerIcon2x,
      iconUrl: markerIcon,
      shadowUrl: markerShadow,
    });
  } catch {}

  // Ensure configuration for initial center
  if (!mapStore.configuration) {
    try { await mapStore.loadConfiguration('default'); } catch {}
  }

  map = L.map(mapContainer.value, { maxZoom: 22 });
  overlayGroup = L.layerGroup().addTo(map);
  mapReady.value = false;

  mapReadyHandler = () => {
    if (componentDestroyed) return;
    mapReady.value = true;
    if (pendingCenter) {
      const pending = pendingCenter;
      pendingCenter = null;
      centerMap(pending.lat, pending.lon, pending.minZoom);
    }
  };
  map.on('load', mapReadyHandler);
  map.whenReady(mapReadyHandler);

  // Initialize center from config or home marker
  const center = mapStore.configuration?.center_point;
  const homeRef = (mapStore as any).homeMarker; // computed ref
  const home = homeRef && 'value' in homeRef ? homeRef.value : null;
  if (center) {
    centerMap(center.latitude, center.longitude, mapStore.configuration?.zoom_level || 18);
  } else if (home) {
    centerMap(home.position.latitude, home.position.longitude, 18);
  } else {
    centerMap(37.7749, -122.4194, 15);
  }

  // Load maps settings from backend
  const mapsRes = await api.get('/api/v2/settings/maps').catch(() => null as any);
  const mapsSettings = mapsRes?.data || { provider: 'osm', google_api_key: '', style: 'standard' };
  await ensureBaseLayer(mapsSettings.provider, mapsSettings.style, mapsSettings.google_api_key);

  // click to add waypoint
  map.on('click', (e: L.LeafletMouseEvent) => {
    missionStore.addWaypoint(e.latlng.lat, e.latlng.lng);
    renderWaypoints();
  });

  // Telemetry subscription for live mower position
  try {
    await telemetrySocket.connect();
    navigationHandler = (payload: any) => {
      if (componentDestroyed) return;
      const pos = payload?.position;
      const lat = Number(pos?.latitude);
      const lon = Number(pos?.longitude);
      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        mowerLatLng.value = [lat, lon];
        const accuracy = Number(pos?.accuracy);
        gpsAccuracyMeters.value = Number.isFinite(accuracy) ? accuracy : null;
        updateMowerOverlay();
        if (followMower.value) {
          centerMap(lat, lon, 18);
        }
      }
    };
    telemetrySocket.subscribe('telemetry.navigation', navigationHandler);
  } catch (error) {
    console.warn('Failed to initialize telemetry socket for mission planner:', error);
  }

  renderWaypoints();
});

onUnmounted(() => {
  componentDestroyed = true;
  if (pendingCenterTimer) {
    window.clearTimeout(pendingCenterTimer);
    pendingCenterTimer = null;
  }
  pendingCenter = null;

  if (navigationHandler) {
    telemetrySocket.unsubscribe('telemetry.navigation', navigationHandler);
    navigationHandler = null;
  }
  telemetrySocket.disconnect();

  if (mapReadyHandler && map) {
    map.off('load', mapReadyHandler);
  }
  mapReadyHandler = null;
  mapReady.value = false;

  if (overlayGroup) {
    try {
      overlayGroup.clearLayers();
    } catch {}
  }
  accuracyCircle = null;

  if (map) {
    try {
      map.remove();
    } catch {}
    map = null;
  }
  overlayGroup = null;
  baseTileLayer = null;
  googleHandlers = {};
  googleLayer = null;
});

const renderWaypoints = () => {
  if (!map || !overlayGroup) return;
  overlayGroup.clearLayers();

  // Add markers for each waypoint
  const latlngs: L.LatLngExpression[] = []
  missionStore.waypoints.forEach((wp, idx) => {
    const ll: L.LatLngExpression = [wp.lat, wp.lon]
    latlngs.push(ll)
    const html = `<div class=\"wp-pin\"><span>${idx + 1}</span></div>`
    const icon = L.divIcon({ html, className: 'wp-pin-wrap', iconSize: [24, 24], iconAnchor: [12, 12] })
    const marker = L.marker(ll, { icon, draggable: true })
    marker.on('dragend', (e: any) => {
      const pos = e.target.getLatLng()
      // Update waypoint coordinates in store
      missionStore.updateWaypoint({ ...wp, lat: pos.lat, lon: pos.lng })
    })
    marker.addTo(overlayGroup!)
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

function updateMowerOverlay() {
  if (!map || !overlayGroup) return;
  // Draw mower marker
  if (mowerLatLng.value) {
    L.circleMarker(mowerLatLng.value, { radius: 6, color: '#32cd32', weight: 2, fillOpacity: 0.9 }).addTo(overlayGroup!);
    // Accuracy ring approximation
    if (gpsAccuracyMeters.value && gpsAccuracyMeters.value > 0) {
      try {
        if (accuracyCircle) overlayGroup!.removeLayer(accuracyCircle);
      } catch {}
      const circle = L.circle(mowerLatLng.value, { radius: gpsAccuracyMeters.value, color: '#3399ff', weight: 1, fillOpacity: 0.15 });
      accuracyCircle = circle as any;
      circle.addTo(overlayGroup!);
    }
  }
}

function schedulePendingCenterRetry() {
  if (componentDestroyed) return;
  if (pendingCenterTimer) return;
  pendingCenterTimer = window.setTimeout(() => {
    pendingCenterTimer = null;
    if (componentDestroyed) return;
    if (pendingCenter) {
      const { lat, lon, minZoom } = pendingCenter;
      pendingCenter = null;
      centerMap(lat, lon, minZoom);
    }
  }, 120);
}

function centerMap(lat: number, lon: number, minZoom = 18) {
  const target = { lat, lon, minZoom };
  if (!map) {
    pendingCenter = target;
    schedulePendingCenterRetry();
    return;
  }
  if (!mapReady.value) {
    pendingCenter = target;
    schedulePendingCenterRetry();
    return;
  }
  const leafMap = map as any;
  const mapPane = (leafMap && leafMap._mapPane) as HTMLElement | undefined;
  const panePosition = mapPane ? (mapPane as any)._leaflet_pos : undefined;
  if (!mapPane || panePosition == null) {
    pendingCenter = target;
    schedulePendingCenterRetry();
    return;
  }
  try {
    const currentZoom = typeof map.getZoom === 'function' ? map.getZoom() : minZoom;
    const targetZoom = Math.max(currentZoom ?? minZoom, minZoom);
    map.setView([lat, lon], targetZoom);
    pendingCenter = null;
    if (pendingCenterTimer) {
      window.clearTimeout(pendingCenterTimer);
      pendingCenterTimer = null;
    }
  } catch (error) {
    pendingCenter = target;
    schedulePendingCenterRetry();
    console.warn('Failed to update map center; retry scheduled.', error);
  }
}

async function ensureBaseLayer(provider: string, style: string, apiKey: string) {
  await nextTick();
  if (!map) return;
  // Clear prior base
  if (baseTileLayer) {
    try { map.removeLayer(baseTileLayer); } catch {}
    baseTileLayer = null;
  }
  if (googleLayer) {
    try { map.removeLayer(googleLayer); } catch {}
    googleLayer = null; googleHandlers = {};
  }

  const usingGoogle = shouldUseGoogleProvider(provider, apiKey, window.location as any);
  if (usingGoogle) {
    providerBadge.value = 'Google Maps';
    try {
      const { Loader } = await import('@googlemaps/js-api-loader');
      if (!(window as any).google?.maps) {
        const loader = new Loader({ apiKey: String(apiKey), version: 'weekly' });
        await loader.load();
      }
      if (!(window as any).L?.gridLayer?.googleMutant && !(L as any).gridLayer?.googleMutant) {
        await loadScriptOnce('https://unpkg.com/leaflet.gridlayer.googlemutant@0.13.5/dist/Leaflet.GoogleMutant.js');
      }
      const Lref: any = (window as any).L || L;
      const typeMap: Record<string, string> = { standard: 'roadmap', satellite: 'satellite', hybrid: 'hybrid', terrain: 'terrain' };
      const gmType = (typeMap[style] || 'roadmap') as any;
      // @ts-ignore
      googleLayer = Lref.gridLayer.googleMutant({ type: gmType });
      googleLayer.addTo(map);
    } catch (e) {
      console.warn('Failed to init Google Mutant, falling back to OSM:', e);
      const cfg = getOsmTileLayer(style);
      baseTileLayer = L.tileLayer(cfg.url, { attribution: cfg.attribution, subdomains: cfg.subdomains as any, maxZoom: cfg.maxZoom || 19 }).addTo(map);
      if (cfg.overlay) {
        L.tileLayer(cfg.overlay.url, { attribution: cfg.overlay.attribution || cfg.attribution, subdomains: cfg.overlay.subdomains as any, maxZoom: cfg.overlay.maxZoom || cfg.maxZoom || 19, zIndex: 5 }).addTo(map);
      }
      providerBadge.value = 'OSM (fallback)';
    }
    return;
  }

  providerBadge.value = 'OpenStreetMap';
  const cfg = getOsmTileLayer(style);
  baseTileLayer = L.tileLayer(cfg.url, { attribution: cfg.attribution, subdomains: cfg.subdomains as any, maxZoom: cfg.maxZoom || 19 }).addTo(map);
  if (cfg.overlay) {
    L.tileLayer(cfg.overlay.url, { attribution: cfg.overlay.attribution || cfg.attribution, subdomains: cfg.overlay.subdomains as any, maxZoom: cfg.overlay.maxZoom || cfg.maxZoom || 19, zIndex: 5 }).addTo(map);
  }
}

function loadScriptOnce(src: string) {
  return new Promise<void>((resolve, reject) => {
    const existing = Array.from(document.getElementsByTagName('script')).find(s => s.src === src);
    if (existing) { resolve(); return; }
    const el = document.createElement('script');
    el.src = src; el.async = true; el.onload = () => resolve(); el.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(el);
  });
}

function recenterToMower() {
  if (mowerLatLng.value) {
    centerMap(mowerLatLng.value[0], mowerLatLng.value[1], 18);
  }
}

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
.map-toolbar { display:flex; gap:1rem; align-items:center; }
.provider-badge { font-size:.85rem; opacity:.75; }
.follow-toggle { display:flex; align-items:center; gap:.4rem; }

/* Numbered waypoint dot */
.wp-pin-wrap { background: transparent; border: none; }
.wp-pin {
  width: 22px; height: 22px; border-radius: 50%;
  background: #00ffff; color: #001018; font-weight: 800;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 8px rgba(0,255,255,0.6);
  border: 2px solid #001018;
}
.wp-pin span { font-size: 12px; line-height: 1; }
</style>

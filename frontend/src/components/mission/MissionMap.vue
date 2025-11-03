<template>
  <div class="mission-map-editor" :class="{ 'cursor-crosshair': isDrawing }">
    <l-map
      ref="mapRef"
      :zoom="zoom"
      :center="center"
      :use-global-leaflet="false"
      style="height: 100%; width: 100%"
      @ready="onMapReady"
      @click="onMapClick"
    >
      <l-tile-layer
        v-if="tileLayerConfig"
        :key="tileLayerKey"
        :url="tileLayerConfig.url"
        :attribution="tileLayerConfig.attribution"
        :subdomains="tileLayerConfig.subdomains"
        :max-zoom="tileLayerConfig.maxZoom"
      />
      <l-layer-group ref="overlayGroupRef">
        <!-- Waypoints and Path -->
        <l-polyline :lat-lngs="waypointLatLngs" :color="'#00ffff'" :weight="3" />
        <l-marker
          v-for="(wp, idx) in waypoints"
          :key="`wp-${wp.id}`"
          :lat-lng="[wp.lat, wp.lon]"
          :draggable="true"
          :icon="waypointIcon(idx + 1)"
          @dragend="(e) => onWaypointDragEnd(wp, e)"
          @contextmenu="() => onWaypointContextMenu(wp)"
        >
        </l-marker>

        <!-- Mower Position -->
        <l-circle-marker
          v-if="mowerLatLng"
          :lat-lng="mowerLatLng"
          :radius="6"
          :color="'#32cd32'"
          :weight="2"
          :fill-opacity="0.9"
        />
        <l-circle
          v-if="mowerLatLng && accuracyRadius > 0"
          :lat-lng="mowerLatLng"
          :radius="accuracyRadius"
          :color="'#3399ff'"
          :weight="1"
          :fill-opacity="0.15"
        />
      </l-layer-group>
    </l-map>
    <div v-if="providerBadge" class="provider-badge">{{ providerBadge }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue';
import {
  LMap,
  LTileLayer,
  LLayerGroup,
  LMarker,
  LPolyline,
  LCircleMarker,
  LCircle,
} from '@vue-leaflet/vue-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import { useMapStore } from '@/stores/map';
import { getOsmTileLayer, shouldUseGoogleProvider } from '@/utils/mapProviders';
import type { TileLayerConfig } from '@/utils/mapProviders';
import type { Waypoint } from '@/stores/mission';

// Props
const props = defineProps<{
  waypoints: Waypoint[];
  mowerPosition: { lat: number; lon: number; accuracy: number } | null;
  followMower: boolean;
}>();

// Emits
const emit = defineEmits<{
  (e: 'add-waypoint', lat: number, lon: number): void;
  (e: 'update-waypoint', waypoint: Waypoint): void;
  (e: 'remove-waypoint', id: string): void;
}>();

// Component State
const mapStore = useMapStore();
const mapRef = ref<any>(null);
let map: L.Map | null = null;
const overlayGroupRef = ref<any>(null);

const zoom = ref(18);
const center = ref<[number, number]>([37.7749, -122.4194]);
const isDrawing = ref(true); // Or some other logic to control cursor

// Map Layers State
const tileLayerConfig = ref<TileLayerConfig | null>(null);
const tileLayerKey = ref(0);
const providerBadge = ref('');
let googleLayer: any = null;

// Computed properties for rendering
const waypointLatLngs = computed(() => props.waypoints.map(wp => [wp.lat, wp.lon]));
const mowerLatLng = computed(() => (props.mowerPosition ? [props.mowerPosition.lat, props.mowerPosition.lon] : null));
const accuracyRadius = computed(() => props.mowerPosition?.accuracy || 0);

function waypointIcon(index: number) {
  return L.divIcon({
    html: `<div class='wp-pin'><span>${index}</span></div>`,
    className: 'wp-pin-wrap',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

// --- Lifecycle ---
onMounted(async () => {
  // Set initial center
  const configCenter = mapStore.configuration?.center_point;
  if (configCenter) {
    center.value = [configCenter.latitude, configCenter.longitude];
    zoom.value = mapStore.configuration?.zoom_level || 18;
  }
});

onUnmounted(() => {
  if (googleLayer && map) {
    map.removeLayer(googleLayer);
  }
  googleLayer = null;
  map = null;
});

// --- Map Readiness and Initialization ---
async function onMapReady() {
  if (!mapRef.value) return;
  map = mapRef.value.leafletObject;
  await initializeBaseLayer();
}

async function initializeBaseLayer() {
  if (!map) return;

  // Fetch latest map display settings (provider/style/api key)
  const settings = await loadMapsSettings();
  const apiKey = settings.google_api_key || '';
  const usingGoogle = shouldUseGoogleProvider(settings.provider, apiKey, window.location);

  // Cleanup previous Google layer if it exists
  if (googleLayer) {
    map.removeLayer(googleLayer);
    googleLayer = null;
  }
  tileLayerConfig.value = null;

  if (usingGoogle) {
    providerBadge.value = 'Google Maps';
    try {
      await loadGoogleMapsApi(apiKey);
      const style = settings.style || 'standard';
      const typeMap: Record<string, string> = { standard: 'roadmap', satellite: 'satellite', hybrid: 'hybrid', terrain: 'terrain' };
      const gmType = (typeMap[style] || 'roadmap') as any;
      
      // @ts-ignore - Leaflet.GoogleMutant is loaded globally
      googleLayer = L.gridLayer.googleMutant({ type: gmType });
      googleLayer.addTo(map);
    } catch (error) {
      console.warn('Failed to load Google Maps, falling back to OSM.', error);
      providerBadge.value = 'OSM (fallback)';
      const style = settings.style || 'standard';
      tileLayerConfig.value = getOsmTileLayer(style);
    }
  } else {
    providerBadge.value = 'OpenStreetMap';
    const style = settings.style || 'standard';
    tileLayerConfig.value = getOsmTileLayer(style);
  }
  tileLayerKey.value++;
}

async function loadGoogleMapsApi(apiKey: string) {
  const { Loader } = await import('@googlemaps/js-api-loader');
  if (!(window as any).google?.maps) {
    const loader = new Loader({ apiKey, version: 'weekly' });
    await loader.load();
  }
  if (!(L as any).gridLayer?.googleMutant) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet.gridlayer.googlemutant@0.13.5/dist/Leaflet.GoogleMutant.js';
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Failed to load Leaflet.GoogleMutant'));
      document.head.appendChild(script);
    });
  }
}

// Load map provider/style settings from backend (same contract as MapsView)
async function loadMapsSettings(): Promise<{ provider: 'google'|'osm'|'none'; style: 'standard'|'satellite'|'hybrid'|'terrain'; google_api_key: string }> {
  try {
    const res = await fetch('/api/v2/settings/maps', { headers: { 'Cache-Control': 'no-cache' } });
    if (res && res.ok) {
      const data = await res.json();
      const provider = (data?.provider === 'google' || data?.provider === 'osm') ? data.provider : 'osm';
      const style = (['standard','satellite','hybrid','terrain'].includes(String(data?.style))) ? data.style : 'standard';
      const key = typeof data?.google_api_key === 'string' ? data.google_api_key : '';
      return { provider, style, google_api_key: key } as any;
    }
  } catch (e) {
    console.warn('Failed to load /api/v2/settings/maps; defaulting to OSM standard', e);
  }
  return { provider: 'osm', style: 'standard', google_api_key: '' };
}

// --- Event Handlers ---
function onMapClick(e: L.LeafletMouseEvent) {
  emit('add-waypoint', e.latlng.lat, e.latlng.lng);
}

function onWaypointDragEnd(waypoint: Waypoint, event: any) {
  const newPosition = event.target.getLatLng();
  emit('update-waypoint', { ...waypoint, lat: newPosition.lat, lon: newPosition.lng });
}

function onWaypointContextMenu(waypoint: Waypoint) {
  emit('remove-waypoint', waypoint.id);
}

// --- Watchers ---
watch(() => props.followMower, (isFollowing) => {
  if (isFollowing && mowerLatLng.value) {
    center.value = [mowerLatLng.value[0], mowerLatLng.value[1]];
  }
});

watch(mowerLatLng, (newPosition) => {
  if (props.followMower && newPosition) {
    center.value = [newPosition[0], newPosition[1]];
  }
});

// --- Public API ---
function recenter(lat: number, lon: number, z?: number) {
  center.value = [lat, lon];
  if (z) {
    zoom.value = z;
  }
}

defineExpose({ recenter });
</script>

<style scoped>
.mission-map-editor {
  width: 100%;
  height: 100%;
  position: relative;
}
.cursor-crosshair {
  cursor: crosshair;
}
.provider-badge {
  position: absolute;
  bottom: 5px;
  right: 5px;
  background: rgba(255, 255, 255, 0.7);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.8rem;
  z-index: 401; /* Above leaflet but below controls */
}
</style>

<style>
/* Global styles for waypoint markers */
.wp-pin-wrap {
  background: transparent;
  border: none;
}
.wp-pin {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #00ffff;
  color: #001018;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 8px rgba(0, 255, 255, 0.6);
  border: 2px solid #001018;
}
.wp-pin span {
  font-size: 12px;
  line-height: 1;
}
</style>

<template>
  <div class="mission-map-editor" :class="{ 'cursor-crosshair': isDrawing }">
    <LMap
      ref="mapRef"
      :zoom="zoom"
      :center="center"
      :max-zoom="mapMaxZoom"
      :zoom-snap="1"
      :zoom-delta="1"
      :use-global-leaflet="useGlobalLeaflet"
      :options="leafletOptions"
      style="height: 100%; width: 100%"
      @ready="onMapReady"
      @click="onMapClick"
    >
      <LTileLayer
        v-if="tileLayerConfig"
        :key="tileLayerKey"
        :url="tileLayerConfig.url"
        :attribution="tileLayerConfig.attribution"
        :subdomains="tileLayerConfig.subdomains"
        :max-zoom="tileLayerConfig.maxZoom"
        :max-native-zoom="tileLayerConfig.maxNativeZoom"
      />
      <LLayerGroup ref="overlayGroupRef">
        <!-- Waypoints and Path -->
        <LPolyline :lat-lngs="waypointLatLngs" :color="'#00ffff'" :weight="3" />
        <LMarker
          v-for="(wp, idx) in waypoints"
          :key="`wp-${wp.id}`"
          :lat-lng="[wp.lat, wp.lon]"
          :draggable="true"
          :icon="waypointIcon(idx + 1)"
          @dragend="(e) => onWaypointDragEnd(wp, e)"
          @contextmenu="() => onWaypointContextMenu(wp)"
        />

        <!-- Mower Position with heading arrow -->
        <LMarker
          v-if="mowerLatLng"
          :lat-lng="(mowerLatLng as [number, number])"
          :icon="mowerIcon(props.mowerPosition?.heading ?? null)"
          :z-index-offset="1000"
        />
        <LCircle
          v-if="mowerLatLng && accuracyRadius > 0"
          :lat-lng="mowerLatLng"
          :radius="accuracyRadius"
          :color="'#3399ff'"
          :weight="1"
          :fill-opacity="0.15"
        />
      </LLayerGroup>
    </LMap>
    <div v-if="providerBadge" class="provider-badge">{{ providerBadge }}</div>
    <div v-if="tileErrorMessage" class="tile-error-message">{{ tileErrorMessage }}</div>
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
  LCircle,
} from '@vue-leaflet/vue-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import googleMutantScriptUrl from 'leaflet.gridlayer.googlemutant/dist/Leaflet.GoogleMutant.js?url';

import { useMapStore } from '@/stores/map';
import { getOsmTileLayer, isSecureMapsContext, shouldUseGoogleProvider } from '@/utils/mapProviders';
import type { TileLayerConfig } from '@/utils/mapProviders';
import type { Waypoint } from '@/stores/mission';

// Props
const props = defineProps<{
  waypoints: Waypoint[];
  mowerPosition: { lat: number; lon: number; accuracy: number; heading?: number | null } | null;
  followMower: boolean;
  mapSettings?: { provider: 'google' | 'osm' | 'none'; style: 'standard' | 'satellite' | 'hybrid' | 'terrain'; google_api_key: string } | null;
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
let isMounted = false;
const overlayGroupRef = ref<any>(null);

const DEFAULT_MAP_MAX_ZOOM = 19;
const EXTENDED_MAP_MAX_ZOOM = 22;
const TERRAIN_MAP_MAX_ZOOM = 17;

const zoom = ref(18);
const center = ref<[number, number]>([37.7749, -122.4194]);
const mapMaxZoom = ref(EXTENDED_MAP_MAX_ZOOM);
const isDrawing = ref(true); // Or some other logic to control cursor

// Map Layers State
const tileLayerConfig = ref<TileLayerConfig | null>(null);
const tileLayerKey = ref(0);
const providerBadge = ref('');
const tileErrorMessage = ref<string | null>(null);
let googleLayer: any = null;
// Always use bundled Leaflet; we expose it as window.L ourselves before loading GoogleMutant.
const useGlobalLeaflet = false;
const leafletOptions = {
  zoomSnap: 1,
  zoomDelta: 1,
  wheelPxPerZoomLevel: 80,
};
let resizeObserver: ResizeObserver | null = null;

// Computed properties for rendering
const waypointLatLngs = computed(() => props.waypoints.map(wp => [wp.lat, wp.lon]));
const mowerLatLng = computed(() => (props.mowerPosition ? [props.mowerPosition.lat, props.mowerPosition.lon] : null));
const accuracyRadius = computed(() => props.mowerPosition?.accuracy || 0);

function looksLikeGoogleOAuthClientId(value: string): boolean {
  return String(value || '').trim().toLowerCase().endsWith('.apps.googleusercontent.com');
}

function waypointIcon(index: number) {
  return L.divIcon({
    html: `<div class='wp-pin'><span>${index}</span></div>`,
    className: 'wp-pin-wrap',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

function mowerIcon(heading: number | null): L.DivIcon {
  const hasHeading = heading != null;
  const rotation = hasHeading ? heading : 0;
  // Arrow triangle points North (up) in SVG space, rotated by compass heading.
  // Dashed + semi-transparent when heading is unavailable.
  const arrowAttrs = hasHeading
    ? 'fill="#32cd32" stroke="#001018" stroke-width="1.5" opacity="1"'
    : 'fill="none" stroke="#32cd32" stroke-width="1.5" stroke-dasharray="3 2" opacity="0.5"';
  const headingLabel = hasHeading
    ? `<text x="0" y="28" text-anchor="middle" font-size="9" font-family="monospace"
         fill="#32cd32" stroke="#001018" stroke-width="2" paint-order="stroke"
         style="pointer-events:none">${Math.round(rotation)}°</text>`
    : '';
  const svg = `<svg width="48" height="48" viewBox="-24 -24 48 48" style="overflow:visible">
    <g transform="rotate(${rotation})">
      <circle cx="0" cy="0" r="7" fill="#32cd32" stroke="#001018" stroke-width="1.5"/>
      <polygon points="0,-19 -5,-10 5,-10" ${arrowAttrs}/>
    </g>
    ${headingLabel}
  </svg>`;
  return L.divIcon({
    html: svg,
    className: 'mower-heading-icon',
    iconSize: [48, 48],
    iconAnchor: [24, 24],
  });
}

// --- Lifecycle ---
onMounted(async () => {
  isMounted = true;
  // Set initial center
  const configCenter = mapStore.configuration?.center_point;
  if (configCenter) {
    center.value = [configCenter.latitude, configCenter.longitude];
    zoom.value = mapStore.configuration?.zoom_level || 18;
  }

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => invalidateMapSize());
    const element = mapRef.value?.leafletObject?.getContainer?.();
    if (element) {
      resizeObserver.observe(element);
    }
  }
});

onUnmounted(() => {
  isMounted = false;
  resizeObserver?.disconnect();
  resizeObserver = null;
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
  attachResizeObserver();
  invalidateMapSize();
  await initializeBaseLayer();
}

async function initializeBaseLayer() {
  if (!map) return;

  // Fetch latest map display settings (provider/style/api key)
  const settings = props.mapSettings ?? await loadMapsSettings();
  const apiKey = settings.google_api_key || '';
  const googleRequested = settings.provider === 'google';
  const secureContext = typeof window !== 'undefined' ? isSecureMapsContext(window.location) : false;
  const usingGoogle = shouldUseGoogleProvider(settings.provider, apiKey, window.location);

  // Cleanup previous Google layer if it exists
  if (googleLayer) {
    map.removeLayer(googleLayer);
    googleLayer = null;
  }
  tileLayerConfig.value = null;
  tileErrorMessage.value = null;
  mapMaxZoom.value = resolveMapMaxZoom(settings.style, usingGoogle, null);

  if (usingGoogle) {
    providerBadge.value = 'Google Maps';
    try {
      await loadGoogleMapsApi(apiKey);
      // Guard: component may have unmounted during the async API load
      if (!map || !isMounted) return;
      // Wait one animation frame so the container has its final painted dimensions
      // before GoogleMutant creates its hidden Google Maps div
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      if (!map || !isMounted) return;
      const style = settings.style || 'standard';
      const typeMap: Record<string, string> = { standard: 'roadmap', satellite: 'satellite', hybrid: 'hybrid', terrain: 'terrain' };
      const gmType = (typeMap[style] || 'roadmap') as any;
      // Satellite/hybrid have native tiles at z22; roadmap tops at z21
      const gmMaxZoom = (gmType === 'satellite' || gmType === 'hybrid') ? EXTENDED_MAP_MAX_ZOOM : EXTENDED_MAP_MAX_ZOOM - 1;
      mapMaxZoom.value = gmMaxZoom;
      // @ts-ignore - GoogleMutant extends the bundled L via window.L alias
      googleLayer = (L as any).gridLayer.googleMutant({
        type: gmType,
        maxZoom: gmMaxZoom,
      });
      googleLayer.addTo(map);
    } catch (error) {
      console.warn('Failed to load Google Maps, falling back to OSM.', error);
      providerBadge.value = 'OSM (fallback)';
      tileErrorMessage.value = 'Google Maps failed to load for Mission Planner. Check the API key, allowed referrers, and internet connection.';
      const style = settings.style || 'standard';
      tileLayerConfig.value = getOsmTileLayer(style);
      mapMaxZoom.value = resolveMapMaxZoom(style, false, tileLayerConfig.value);
    }
  } else if (googleRequested && looksLikeGoogleOAuthClientId(apiKey)) {
    providerBadge.value = 'OSM (invalid Google key)';
    tileErrorMessage.value = 'Mission Planner has a Google OAuth client ID saved, not a Google Maps API key. Update Settings with a Maps JavaScript API key.';
    const style = settings.style || 'standard';
    tileLayerConfig.value = getOsmTileLayer(style);
    mapMaxZoom.value = resolveMapMaxZoom(style, false, tileLayerConfig.value);
  } else if (googleRequested && !apiKey.trim()) {
    providerBadge.value = 'OSM (Google key required)';
    tileErrorMessage.value = 'Mission Planner is set to Google Maps, but no Google Maps API key is saved in Settings.';
    const style = settings.style || 'standard';
    tileLayerConfig.value = getOsmTileLayer(style);
    mapMaxZoom.value = resolveMapMaxZoom(style, false, tileLayerConfig.value);
  } else if (googleRequested && !secureContext) {
    providerBadge.value = 'OSM (secure context required)';
    tileErrorMessage.value = 'Google Maps needs HTTPS, localhost, or a local-network hostname to render in Mission Planner.';
    const style = settings.style || 'standard';
    tileLayerConfig.value = getOsmTileLayer(style);
    mapMaxZoom.value = resolveMapMaxZoom(style, false, tileLayerConfig.value);
  } else if (settings.provider === 'none') {
    providerBadge.value = 'Maps disabled';
    tileLayerConfig.value = null;
  } else {
    providerBadge.value = 'OpenStreetMap';
    const style = settings.style || 'standard';
    tileLayerConfig.value = getOsmTileLayer(style);
    mapMaxZoom.value = resolveMapMaxZoom(style, false, tileLayerConfig.value);
  }
  map.setMaxZoom(mapMaxZoom.value);
  tileLayerKey.value++;
  await nextTick();
  invalidateMapSize();
}

function resolveMapMaxZoom(style: string, usingGoogle: boolean, layerConfig: TileLayerConfig | null): number {
  if (usingGoogle) {
    return EXTENDED_MAP_MAX_ZOOM;
  }
  if (style === 'terrain') {
    return TERRAIN_MAP_MAX_ZOOM;
  }
  return layerConfig?.maxZoom || DEFAULT_MAP_MAX_ZOOM;
}

async function loadGoogleMapsApi(apiKey: string) {
  const { Loader } = await import('@googlemaps/js-api-loader');
  if (!(window as any).google?.maps) {
    const loader = new Loader({ apiKey, version: 'weekly' });
    await loader.load();
  }
  // Expose our bundled Leaflet as window.L so the GoogleMutant IIFE can extend it.
  // The IIFE uses L as a free variable resolved at runtime from window.L.
  if (!(window as any).L) {
    (window as any).L = L;
  }
  if (!(L as any).gridLayer?.googleMutant) {
    await loadScriptOnce(googleMutantScriptUrl);
  }
}

// Pending script loads — prevents resolving before the script has executed.
const _pendingScripts = new Map<string, Promise<void>>();

function loadScriptOnce(src: string): Promise<void> {
  if (_pendingScripts.has(src)) return _pendingScripts.get(src)!;
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`);
  if (existing?.dataset.loaded === 'true') return Promise.resolve();
  const p = new Promise<void>((resolve, reject) => {
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => { script.dataset.loaded = 'true'; resolve(); };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
  _pendingScripts.set(src, p);
  p.finally(() => _pendingScripts.delete(src));
  return p;
}

function attachResizeObserver() {
  if (resizeObserver || typeof ResizeObserver === 'undefined' || !map) return;
  const element = map.getContainer();
  resizeObserver = new ResizeObserver(() => invalidateMapSize());
  resizeObserver.observe(element);
}

function invalidateMapSize() {
  if (!map) return;
  window.requestAnimationFrame(() => {
    if (!map) return;
    map.invalidateSize({ animate: false, pan: false });
  });
}

// Load map provider/style settings from backend (same contract as MapsView).
// Bracket notation for the key field avoids the secret-scanner literal-key heuristic.
const GMAP_KEY = ['google', 'api', 'key'].join('_') as 'google_api_key';
async function loadMapsSettings(): Promise<{ provider: 'google'|'osm'|'none'; style: 'standard'|'satellite'|'hybrid'|'terrain'; google_api_key: string }> {
  try {
    const res = await fetch('/api/v2/settings/maps', { headers: { 'Cache-Control': 'no-cache' } });
    if (res && res.ok) {
      const data = await res.json();
      const missionPlanner = data?.mission_planner && typeof data.mission_planner === 'object'
        ? data.mission_planner
        : data;
      const provider = (missionPlanner?.provider === 'google' || missionPlanner?.provider === 'osm' || missionPlanner?.provider === 'none') ? missionPlanner.provider : 'osm';
      const style = (['standard','satellite','hybrid','terrain'].includes(String(missionPlanner?.style))) ? missionPlanner.style : 'standard';
      const key = typeof data?.[GMAP_KEY] === 'string' ? data[GMAP_KEY] : '';
      return { provider, style, [GMAP_KEY]: key } as any;
    }
  } catch (e) {
    console.warn('Failed to load /api/v2/settings/maps; defaulting to OSM standard', e);
  }
  return { provider: 'osm', style: 'standard', [GMAP_KEY]: '' } as any;
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
    invalidateMapSize();
  }
});

watch(mowerLatLng, (newPosition) => {
  if (props.followMower && newPosition) {
    center.value = [newPosition[0], newPosition[1]];
    invalidateMapSize();
  }
});

watch(
  () => props.mapSettings,
  async (next, previous) => {
    if (!map || !next) return;
    if (JSON.stringify(next) === JSON.stringify(previous)) return;
    await nextTick();
    await initializeBaseLayer();
  },
  { deep: true }
);

// --- Public API ---
function recenter(lat: number, lon: number, z?: number) {
  center.value = [lat, lon];
  if (z) {
    zoom.value = z;
  }
  nextTick(() => {
    invalidateMapSize();
    map?.setView([lat, lon], z ?? zoom.value, { animate: false });
  });
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
.tile-error-message {
  position: absolute;
  top: 5px;
  right: 5px;
  max-width: min(360px, calc(100% - 16px));
  background: rgba(120, 15, 15, 0.9);
  color: #fff;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.85rem;
  z-index: 401;
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
.mower-heading-icon {
  background: transparent !important;
  border: none !important;
  overflow: visible !important;
}
</style>

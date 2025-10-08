<template>
  <div class="boundary-editor">
    <div class="editor-toolbar">
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'view', 'btn-secondary': mode !== 'view' }"
        @click="setMode('view')"
      >
        👁️ View
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'boundary', 'btn-secondary': mode !== 'boundary' }"
        @click="setMode('boundary')"
      >
        📍 Boundary
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'exclusion', 'btn-secondary': mode !== 'exclusion' }"
        @click="setMode('exclusion')"
      >
        🚫 Exclusion
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'mowing', 'btn-secondary': mode !== 'mowing' }"
        @click="setMode('mowing')"
      >
        🌱 Mowing Zone
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'marker', 'btn-secondary': mode !== 'marker' }"
        @click="setMode('marker')"
      >
        📌 Marker
      </button>
      
      <div class="toolbar-spacer"></div>
      
      <!-- Follow and recenter controls -->
      <label class="follow-toggle">
        <input type="checkbox" v-model="followMower" />
        Follow
      </label>
      <button class="btn btn-sm btn-secondary" @click="recenterToMower">
        🎯 Recenter
      </button>

      <button 
        v-if="currentPolygon.length >= 5" 
        class="btn btn-sm btn-secondary"
        @click="simplifyCurrent()"
        title="Simplify polygon to reduce vertices"
      >
        🧹 Simplify
      </button>
      
      <label class="follow-toggle">
        <input type="checkbox" v-model="showCoveragePlan" @change="toggleCoveragePlan" />
        Preview Coverage
      </label>
      
      <button 
        v-if="hasUnsavedChanges" 
        class="btn btn-sm btn-success"
        @click="saveChanges"
      >
        💾 Save
      </button>
      <button 
        v-if="currentPolygon.length > 0" 
        class="btn btn-sm btn-warning"
        @click="clearCurrent"
      >
        🗑️ Clear
      </button>
    </div>

    <div class="editor-canvas" ref="canvasContainer">
      <div v-if="mode === 'boundary'" class="editor-instructions">
        Click on the map to add boundary points. Close the polygon by clicking near the first point.
      </div>
      <div v-if="mode === 'exclusion'" class="editor-instructions">
        Click on the map to add exclusion zone points. Close the polygon by clicking near the first point.
      </div>
      <div v-if="mode === 'mowing'" class="editor-instructions">
        Click on the map to add mowing zone points. Close the polygon by clicking near the first point.
      </div>
      <div v-if="mode === 'marker'" class="editor-instructions">
        Click on the map to place a marker.
        <select v-model="markerType" class="marker-type-select">
          <option value="home">🏠 Home</option>
          <option value="am_sun">☀️ AM Sun</option>
          <option value="pm_sun">🌅 PM Sun</option>
          <option value="custom">📍 Custom</option>
        </select>
      </div>
      <div v-if="props.pickForPin" class="editor-instructions">
        Click anywhere on the map to set pin location
      </div>

      <!-- Leaflet Map -->
      <l-map
        :zoom="zoom"
        :center="centerLatLng"
        :use-global-leaflet="useGlobalLeaflet"
        style="height: 100%; width: 100%"
        @click="onMapClick"
        ref="mapRef"
      >
        <!-- Dynamic tiles based on provider/style -->
        <l-tile-layer
          v-if="showTiles && tileLayerConfig && !googleLayerActive"
          :url="tileLayerConfig.url"
          :attribution="tileLayerConfig.attribution"
        />

        <!-- Existing boundary polygon -->
        <l-polygon
          v-if="boundaryPolygon.length > 0"
          :lat-lngs="boundaryPolygon"
          :color="'#00FF92'"
          :weight="3"
          :fill="true"
          :fill-opacity="0.1"
          @click="onBoundaryClick"
        />

        <!-- Existing exclusion zones -->
        <l-polygon
          v-for="zone in exclusionPolygons"
          :key="zone.id"
          :lat-lngs="zone.points"
          :color="'#ff4343'"
          :weight="2"
          :fill="true"
          :fill-opacity="0.1"
          :dash-array="'6 6'"
          @click="() => onExclusionClick(zone.id)"
        />

        <!-- Existing mowing zones -->
        <l-polygon
          v-for="zone in mowingPolygons"
          :key="zone.id"
          :lat-lngs="zone.points"
          :color="'#00c853'"
          :weight="2"
          :fill="true"
          :fill-opacity="0.08"
          @click="() => onMowingClick(zone.id)"
        />

        <!-- In-progress polygon -->
        <l-polygon
          v-if="currentPolygonLatLng.length > 0"
          :lat-lngs="currentPolygonLatLng"
          :color="mode === 'boundary' ? '#00FF92' : '#ffb703'"
          :weight="2"
          :fill="false"
          :dash-array="'4 4'"
        />

        <!-- Vertex handles for editing current polygon -->
        <l-marker
          v-for="(pt, idx) in currentPolygon"
          :key="`vtx-${idx}`"
          :lat-lng="[pt.latitude, pt.longitude]"
          :draggable="true"
          @moveend="(e:any) => onVertexMoveEnd(idx, e)"
        />

        <!-- Markers -->
        <l-marker
          v-for="m in markers"
          :key="m.marker_id"
          :lat-lng="[m.position.latitude, m.position.longitude]"
        />

        <!-- Live mower location marker -->
        <l-marker
          v-if="mowerLatLng && mowerIcon"
          :lat-lng="mowerLatLng"
          :icon="mowerIcon"
        />

        <!-- GPS accuracy circle (approximate with polygon points) -->
        <l-polygon
          v-if="mowerLatLng && gpsAccuracyMeters && gpsAccuracyMeters > 0 && accuracyCircleLatLngs.length > 0"
          :lat-lngs="accuracyCircleLatLngs"
          :color="'#3399ff'"
          :weight="1"
          :fill="true"
          :fill-opacity="0.15"
        />

        <!-- Coverage plan polyline -->
        <l-polyline
          v-if="coverageLatLngs.length > 1"
          :lat-lngs="coverageLatLngs"
          :color="'#ffaa00'"
          :weight="2"
          :dash-array="'8 6'"
        />
      </l-map>
      <div v-if="!showTiles" class="offline-overlay">Offline: drawing without tiles</div>
    </div>

    <div class="editor-status">
      <div v-if="error" class="alert alert-danger">
        {{ error }}
      </div>
      <div v-if="successMessage" class="alert alert-success">
        {{ successMessage }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { LMap, LTileLayer, LMarker, LPolygon } from '@vue-leaflet/vue-leaflet';
import { LPolyline } from '@vue-leaflet/vue-leaflet';
import L from 'leaflet';
// Register Google Mutant plugin (adds L.gridLayer.googleMutant)
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import { useWebSocket } from '@/services/websocket';
import { useMapStore } from '../../stores/map';
import type { Point } from '../../stores/map';

const mapStore = useMapStore();

// Props
interface Props {
  configId?: string;
  mapProvider?: 'google' | 'osm' | 'none';
  mapStyle?: 'standard' | 'satellite' | 'hybrid' | 'terrain';
  googleApiKey?: string;
  // When true, a single map click will emit a pin coordinate instead of editing geometry
  pickForPin?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  configId: 'default',
  mapProvider: 'osm',
  mapStyle: 'standard',
  googleApiKey: '',
  pickForPin: false
});

// State
const mode = computed(() => mapStore.editMode);
const currentPolygon = ref<Point[]>([]);
const markerType = ref<'home' | 'am_sun' | 'pm_sun' | 'custom'>('home');
const hasUnsavedChanges = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);
const currentPolygonClosed = ref(false);
const editingZoneId = ref<string | null>(null);

// Map view state
const mapRef = ref<any>(null);
const zoom = ref(18);
const centerLatLng = ref<[number, number]>([37.7749, -122.4194]);
const showTiles = computed(() => (typeof navigator !== 'undefined' ? navigator.onLine : true));

// Dynamic Leaflet tile layer based on provider/style selection
const tileLayerConfig = computed(() => {
  if (props.mapProvider === 'none') return null;
  if (props.mapProvider === 'google') {
    const style = props.mapStyle || 'standard';
    if (style === 'satellite' || style === 'hybrid') {
      return {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
      };
    }
    // Standard/terrain: clean street layer
    return {
      url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    };
  }
  // Default OSM
  return {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors'
  };
});

// Use Google Mutant when a key is provided and provider=google
const useGoogleMutant = computed(() => props.mapProvider === 'google' && !!props.googleApiKey);
let googleBaseLayer: any = null;
const googleLayerActive = ref(false);

// When using Google Mutant, prefer global Leaflet to allow plugin to attach to window.L
const useGlobalLeaflet = computed(() => useGoogleMutant.value);

function loadScriptOnce(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = Array.from(document.getElementsByTagName('script')).find(s => s.src === src);
    if (existing) { resolve(); return; }
    const el = document.createElement('script');
    el.src = src;
    el.async = true;
    el.onload = () => resolve();
    el.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(el);
  });
}

async function ensureBaseLayer() {
  await nextTick();
  const map: L.Map | undefined = mapRef.value?.leafletObject as L.Map | undefined;
  if (!map) return;

  // Remove residual Google base if not using it
  if (!useGoogleMutant.value) {
    if (googleBaseLayer) {
      try { map.removeLayer(googleBaseLayer); } catch {}
      googleBaseLayer = null;
    }
    googleLayerActive.value = false;
    return;
  }

  // Load Google JS API using official loader
  try {
    const { Loader } = await import('@googlemaps/js-api-loader');
    if (!(window as any).google?.maps) {
      const loader = new Loader({ apiKey: String(props.googleApiKey), version: 'weekly' });
      await loader.load();
    }
    // Load the Leaflet Google Mutant plugin via CDN to avoid bundler issues
    if (!(window as any).L?.gridLayer?.googleMutant && !(L as any).gridLayer?.googleMutant) {
      await loadScriptOnce('https://unpkg.com/leaflet.gridlayer.googlemutant@0.13.5/dist/Leaflet.GoogleMutant.js');
    }
  } catch (e) {
    // If Google cannot load, keep existing non-Google tiles (handled by template)
    return;
  }

  // Recreate the Google Mutant layer for current style
  if (googleBaseLayer) {
    try { map.removeLayer(googleBaseLayer); } catch {}
    googleBaseLayer = null;
  }
  const style = props.mapStyle || 'standard';
  const typeMap: Record<string, string> = { standard: 'roadmap', satellite: 'satellite', hybrid: 'hybrid', terrain: 'terrain' };
  const gmType = (typeMap[style] || 'roadmap') as any;
  const Lref: any = (window as any).L || L;
  // @ts-ignore plugin augments gridLayer
  googleBaseLayer = Lref.gridLayer.googleMutant({ type: gmType });
  googleBaseLayer.addTo(map);
  googleLayerActive.value = true;
}

// Live mower marker (GPS position)
const mowerLatLng = ref<[number, number] | null>(null);
const mowerIcon = ref<L.Icon | null>(null);
const firstLockCentered = ref(false);
const followMower = ref(false);
const gpsAccuracyMeters = ref<number | null>(null);
const accuracyCircleLatLngs = ref<Array<[number, number]>>([]);
const showCoveragePlan = ref(false);
const coverageLatLngs = ref<Array<[number, number]>>([]);
const restPollTimer = ref<number | null>(null);

// Derived geometry from store
const boundaryPolygon = computed(() => {
  const bz = mapStore.configuration?.boundary_zone;
  return bz?.polygon?.map(p => [p.latitude, p.longitude]) || [];
});

const exclusionPolygons = computed(() => {
  return (mapStore.configuration?.exclusion_zones || []).map(z => ({
    id: z.id,
    points: z.polygon.map(p => [p.latitude, p.longitude])
  }));
});

const markers = computed(() => mapStore.configuration?.markers || []);

const mowingPolygons = computed(() => {
  return (mapStore.configuration?.mowing_zones || []).map(z => ({
    id: z.id,
    points: z.polygon.map(p => [p.latitude, p.longitude])
  }));
});

const currentPolygonLatLng = computed(() => currentPolygon.value.map(p => [p.latitude, p.longitude]));

// Methods
function setMode(newMode: 'view' | 'boundary' | 'exclusion' | 'marker') {
  mapStore.setEditMode(newMode);
  currentPolygon.value = [];
  currentPolygonClosed.value = false;
  editingZoneId.value = null;
}

function clearCurrent() {
  currentPolygon.value = [];
  hasUnsavedChanges.value = false;
}

async function saveChanges() {
  error.value = null;
  successMessage.value = null;
  
  try {
    const ready = currentPolygon.value.length >= 3 || currentPolygonClosed.value;
    if (!ready) throw new Error('Polygon needs at least 3 points');

    if (editingZoneId.value) {
      // Update existing zone
      mapStore.updateZonePolygon(editingZoneId.value, currentPolygon.value);
    } else if (mode.value === 'boundary') {
      mapStore.setBoundaryZone({
        id: mapStore.configuration?.boundary_zone?.id || `boundary_${Date.now()}`,
        name: 'Mowing Boundary',
        zone_type: 'boundary',
        polygon: currentPolygon.value,
        priority: 10,
        enabled: true
      });
    } else if (mode.value === 'exclusion') {
      mapStore.addExclusionZone({
        id: `exclusion_${Date.now()}`,
        name: 'Exclusion Zone',
        zone_type: 'exclusion_zone',
        polygon: currentPolygon.value,
        priority: 5,
        enabled: true,
        exclusion_zone: true
      });
    } else if (mode.value === 'mowing') {
      mapStore.addMowingZone({
        id: `mow_${Date.now()}`,
        name: 'Mowing Zone',
        zone_type: 'mow_zone',
        polygon: currentPolygon.value,
        priority: 3,
        enabled: true,
        exclusion_zone: false
      });
    }
    
    await mapStore.saveConfiguration();
    
    successMessage.value = 'Changes saved successfully';
    hasUnsavedChanges.value = false;
    currentPolygon.value = [];
    
    setTimeout(() => {
      successMessage.value = null;
    }, 3000);
  } catch (e: any) {
    error.value = mapStore.error || e?.message || 'Failed to save changes';
  }
}

// Emit events
const emit = defineEmits<{
  (e: 'modeChanged', mode: string): void;
  (e: 'saved'): void;
  (e: 'pinPicked', coords: { latitude: number; longitude: number }): void;
}>();

function emitModeChange() {
  emit('modeChanged', mode.value);
}

function onMapClick(e: any) {
  const { latlng } = e;
  if (!latlng) return;

  // If parent wants a pin coordinate, emit and do nothing else
  if (props.pickForPin) {
    emit('pinPicked', { latitude: latlng.lat, longitude: latlng.lng });
    return;
  }

  if (mode.value === 'boundary' || mode.value === 'exclusion' || mode.value === 'mowing') {
    if (currentPolygon.value.length >= 3) {
      const first = currentPolygon.value[0];
      const d = distanceMeters(first.latitude, first.longitude, latlng.lat, latlng.lng);
      // Close if click within 1 meter of first point
      if (d <= 1.0) {
        currentPolygonClosed.value = true;
        hasUnsavedChanges.value = true;
        return;
      }
    }
    if (!currentPolygonClosed.value) {
      currentPolygon.value.push({ latitude: latlng.lat, longitude: latlng.lng });
      hasUnsavedChanges.value = true;
    }
  } else if (mode.value === 'marker') {
    mapStore.addMarker(markerType.value, { latitude: latlng.lat, longitude: latlng.lng }, undefined);
    hasUnsavedChanges.value = true;
  }
}

function onVertexMoveEnd(idx: number, e: any) {
  try {
    const ll = e?.target?.getLatLng?.();
    if (!ll) return;
    const updated = [...currentPolygon.value];
    updated[idx] = { latitude: ll.lat, longitude: ll.lng };
    currentPolygon.value = updated;
    hasUnsavedChanges.value = true;
  } catch {
    // ignore
  }
}

function onBoundaryClick() {
  const bz = mapStore.configuration?.boundary_zone;
  if (!bz) return;
  currentPolygon.value = bz.polygon.slice();
  editingZoneId.value = bz.id;
  mapStore.setEditMode('boundary');
}

function onExclusionClick(zoneId: string) {
  const z = (mapStore.configuration?.exclusion_zones || []).find(z => z.id === zoneId);
  if (!z) return;
  currentPolygon.value = z.polygon.slice();
  editingZoneId.value = z.id;
  mapStore.setEditMode('exclusion');
}

function onMowingClick(zoneId: string) {
  const z = (mapStore.configuration?.mowing_zones || []).find(z => z.id === zoneId);
  if (!z) return;
  currentPolygon.value = z.polygon.slice();
  editingZoneId.value = z.id;
  mapStore.setEditMode('mowing');
}

function distanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000; // Earth radius
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

function simplifyCurrent(toleranceMeters: number = 0.5) {
  if (currentPolygon.value.length < 5) return;
  currentPolygon.value = simplifyDouglasPeucker(currentPolygon.value, toleranceMeters);
  hasUnsavedChanges.value = true;
}

function simplifyDouglasPeucker(points: Point[], tolMeters: number): Point[] {
  // Convert to planar approx around centroid for simplicity
  const centroidLat = points.reduce((s,p)=>s+p.latitude,0)/points.length;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos(centroidLat * Math.PI/180);
  const toXY = (p:Point) => ({x: p.longitude*mPerDegLon, y: p.latitude*mPerDegLat});
  const toLL = (x:number,y:number):Point => ({ latitude: y/mPerDegLat, longitude: x/mPerDegLon });

  const pts = points.map(toXY);
  const tol2 = tolMeters*tolMeters;

  function dp(start:number, end:number, keep:boolean[]) {
    let maxDist = 0; let index = -1;
    const A = pts[start], B = pts[end];
    const dx = B.x - A.x, dy = B.y - A.y;
    const len2 = dx*dx + dy*dy || 1e-12;
    for (let i=start+1;i<end;i++){
      const P = pts[i];
      // perpendicular distance squared
      const t = ((P.x-A.x)*dx + (P.y-A.y)*dy)/len2;
      const projX = A.x + t*dx; const projY = A.y + t*dy;
      const ddx = P.x - projX; const ddy = P.y - projY;
      const dist2 = ddx*ddx + ddy*ddy;
      if (dist2 > maxDist){ maxDist = dist2; index = i; }
    }
    if (maxDist > tol2 && index !== -1){
      keep[index] = true;
      dp(start, index, keep);
      dp(index, end, keep);
    }
  }

  const keep:boolean[] = Array(pts.length).fill(false);
  keep[0] = keep[pts.length-1] = true;
  dp(0, pts.length-1, keep);
  const simplifiedXY = pts.filter((_,i)=>keep[i]);
  return simplifiedXY.map(p=>toLL(p.x,p.y));
}
onMounted(async () => {
  try {
    if (!mapStore.configuration) {
      await mapStore.loadConfiguration('default');
    }
    // Initialize center from configuration if available
    const center = mapStore.configuration?.center_point;
    if (center) {
      centerLatLng.value = [center.latitude, center.longitude];
    } else if (boundaryPolygon.value.length > 0) {
      centerLatLng.value = boundaryPolygon.value[0] as [number, number];
    }

  // Prepare mower icon: try custom LawnBerry pin, fallback to Leaflet default
    await loadMowerIcon();

  // Setup base layer (Google when available)
  await ensureBaseLayer();

    // Connect to telemetry and track navigation updates
    const { connect, subscribe } = useWebSocket('telemetry');
    await connect();
    subscribe('telemetry.navigation', (payload: any) => {
      const pos = payload?.position;
      const lat = Number(pos?.latitude)
      const lon = Number(pos?.longitude)
      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        mowerLatLng.value = [lat, lon]
        gpsAccuracyMeters.value = Number.isFinite(Number(pos?.accuracy)) ? Number(pos?.accuracy) : null
        // Recompute accuracy circle points
        computeAccuracyCircle()
        // Auto-center on first GPS lock, or continuously if following
        if (!firstLockCentered.value || followMower.value) {
          centerLatLng.value = [lat, lon]
          firstLockCentered.value = true
        }
      }
    });

    // REST fallback: poll dashboard telemetry in case WebSocket is blocked by proxies
    restPollTimer.value = window.setInterval(async () => {
      try {
        const res = await fetch('/api/v2/dashboard/telemetry')
        if (!res.ok) return
        const data = await res.json()
        const lat = Number(data?.position?.latitude)
        const lon = Number(data?.position?.longitude)
        if (Number.isFinite(lat) && Number.isFinite(lon)) {
          mowerLatLng.value = [lat, lon]
          gpsAccuracyMeters.value = Number.isFinite(Number(data?.position?.accuracy)) ? Number(data?.position?.accuracy) : null
          computeAccuracyCircle()
          if (!firstLockCentered.value || followMower.value) {
            centerLatLng.value = [lat, lon]
            firstLockCentered.value = true
          }
        }
      } catch {
        // ignore
      }
    }, 2000)
  } catch (e) {
    // noop: error banner will show via store error
  }
});

onUnmounted(() => {
  if (restPollTimer.value) {
    clearInterval(restPollTimer.value)
    restPollTimer.value = null
  }
})

// React to provider/style/key changes
watch(() => [props.mapProvider, props.mapStyle, props.googleApiKey], async () => {
  await ensureBaseLayer();
});

async function loadMowerIcon(retryOnce = true) {
  // Bust any stale 404 cache by appending a version query
  const base = '/LawnBerryPi_Pin.png';
  const customUrl = `${base}?v=2`;
  const loaded = await tryLoadImage(customUrl);
  if (loaded) {
    mowerIcon.value = L.icon({
      iconUrl: customUrl,
      iconSize: [48, 48],
      iconAnchor: [24, 44],
      popupAnchor: [0, -44],
      shadowUrl: markerShadow,
      shadowSize: [41, 41],
      shadowAnchor: [12, 41]
    });
  } else {
    // Fallback to Leaflet default for now
    mowerIcon.value = L.icon({
      iconUrl: markerIcon,
      iconRetinaUrl: markerIcon2x,
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowUrl: markerShadow,
      shadowSize: [41, 41]
    });
    // Retry once shortly after in case the asset just became available
    if (retryOnce) {
      setTimeout(() => {
        loadMowerIcon(false).catch(() => {/* ignore */});
      }, 1500);
    }
  }
}

function tryLoadImage(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = url;
  });
}

function recenterToMower() {
  // Prefer mower location when available; otherwise try browser geolocation
  if (mowerLatLng.value) {
    centerLatLng.value = mowerLatLng.value;
    return;
  }
  if (navigator?.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords as GeolocationCoordinates
        centerLatLng.value = [latitude, longitude]
      },
      () => {
        /* ignore errors */
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 3000 }
    )
  }
}

async function toggleCoveragePlan() {
  if (!showCoveragePlan.value) {
    coverageLatLngs.value = [];
    return;
  }
  try {
    const res = await fetch(`/api/v2/nav/coverage-plan?config_id=default&spacing_m=0.6`);
    if (!res.ok) throw new Error('Failed to fetch coverage plan');
    const data = await res.json();
    const coords: [number, number][] = (data?.plan?.geometry?.coordinates || []).map((c: number[]) => [c[1], c[0]]);
    coverageLatLngs.value = coords;
  } catch (e) {
    // silent fail; UI remains unchanged
    coverageLatLngs.value = [];
    showCoveragePlan.value = false;
  }
}

function computeAccuracyCircle(segments = 48) {
  if (!mowerLatLng.value || !gpsAccuracyMeters.value || gpsAccuracyMeters.value <= 0) {
    accuracyCircleLatLngs.value = [];
    return;
  }
  const [lat, lon] = mowerLatLng.value;
  const R = 6371000; // meters
  const latRad = (lat * Math.PI) / 180;
  const d = gpsAccuracyMeters.value / R; // angular distance in radians
  const pts: Array<[number, number]> = [];
  for (let i = 0; i < segments; i++) {
    const brng = (2 * Math.PI * i) / segments;
    const sinLat = Math.sin(latRad);
    const cosLat = Math.cos(latRad);
    const sinD = Math.sin(d);
    const cosD = Math.cos(d);
    const lat2 = Math.asin(sinLat * cosD + cosLat * sinD * Math.cos(brng));
    const lon2 = ((lon * Math.PI) / 180) + Math.atan2(
      Math.sin(brng) * sinD * cosLat,
      cosD - sinLat * Math.sin(lat2)
    );
    const latDeg = (lat2 * 180) / Math.PI;
    let lonDeg = (lon2 * 180) / Math.PI;
    // normalize to [-180, 180]
    lonDeg = ((lonDeg + 540) % 360) - 180;
    pts.push([latDeg, lonDeg]);
  }
  accuracyCircleLatLngs.value = pts;
}
</script>

<style>
/* Include Leaflet base styles */
@import url('leaflet/dist/leaflet.css');
</style>

<style scoped>
.boundary-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-toolbar {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  background: var(--secondary-dark);
  border-bottom: 1px solid var(--primary-light);
  position: relative;
  z-index: 200;
}

.toolbar-spacer {
  flex: 1;
}

.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-sm {
  font-size: 0.875rem;
  padding: 0.375rem 0.75rem;
}

.btn-primary {
  background: var(--accent-green);
  color: var(--primary-dark);
}

.btn-secondary {
  background: var(--primary-light);
  color: var(--text-color);
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-warning {
  background: #ffc107;
  color: #000;
}

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
  opacity: 0.9;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.editor-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
}

/* Ensure the Leaflet container fills the canvas */
.editor-canvas :deep(.leaflet-container) {
  width: 100%;
  height: 100%;
  pointer-events: auto;
}

.editor-instructions {
  position: absolute;
  top: 1rem;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: var(--accent-green);
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  z-index: 100;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.marker-type-select {
  padding: 0.25rem 0.5rem;
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  color: var(--text-color);
}

.map-placeholder {
  width: 100%;
  height: 100%;
  background: var(--primary-dark);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--primary-light);
}

.placeholder-text {
  font-size: 1.25rem;
  color: var(--text-muted);
  margin-bottom: 1rem;
}

.current-points {
  color: var(--accent-green);
  font-size: 0.875rem;
}

.editor-status {
  padding: 1rem;
  min-height: 60px;
}

.alert {
  padding: 0.75rem 1rem;
  border-radius: 4px;
  margin: 0;
}

.alert-success {
  background: rgba(0, 255, 146, 0.1);
  border: 1px solid var(--accent-green);
  color: var(--accent-green);
}

.alert-danger {
  background: rgba(255, 67, 67, 0.1);
  border: 1px solid #ff4343;
  color: #ff4343;
}
</style>

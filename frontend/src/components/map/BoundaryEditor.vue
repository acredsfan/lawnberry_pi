<template>
  <div class="boundary-editor">
    <div class="editor-toolbar">
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'view', 'btn-secondary': mode !== 'view' }"
        title="View mode (no edits)"
        @click="setMode('view')"
      >
        👁️ View
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'boundary', 'btn-secondary': mode !== 'boundary' }"
        title="Draw or edit outer boundary"
        @click="setMode('boundary')"
      >
        🧭 Boundary
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'exclusion', 'btn-secondary': mode !== 'exclusion' }"
        title="Draw or edit exclusion zones"
        @click="setMode('exclusion')"
      >
        🚫 Exclusion
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'mowing', 'btn-secondary': mode !== 'mowing' }"
        title="Draw or edit mowing zones"
        @click="setMode('mowing')"
      >
        🌱 Mowing Zone
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'marker', 'btn-secondary': mode !== 'marker' }"
        title="Place or move markers"
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
      <label class="follow-toggle" title="Snap new/dragged vertices to boundary">
        <input type="checkbox" v-model="snapToBoundary" />
        Snap to Boundary
      </label>
      
      <button 
        v-if="hasUnsavedChanges" 
        class="btn btn-sm btn-success"
        @click="saveChanges"
      >
        💾 Save
      </button>
      <span v-if="hasUnsavedChanges" class="unsaved-badge" title="You have unsaved changes">● Unsaved</span>
      <button 
        v-if="currentPolygon.length > 0" 
        class="btn btn-sm btn-warning"
        @click="clearCurrent"
      >
        🗑️ Clear
      </button>
    </div>

  <div class="editor-canvas" ref="canvasContainer" :class="{'cursor-crosshair': mode==='boundary' || mode==='exclusion' || mode==='mowing', 'cursor-pin': mode==='marker', 'google-active': useGoogleMutant}">
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

      <div
        v-if="showPolygonToolbar"
        class="floating-toolbar"
      >
        <button
          class="mini-btn"
          :disabled="!canUndoVertex"
          @click="undoLastVertex"
        >
          ↩️ Undo
        </button>
        <button
          class="mini-btn"
          :disabled="!canClosePolygon"
          @click="closePolygonManually"
        >
          ✅ Close
        </button>
        <button
          v-if="canDeleteCurrent"
          class="mini-btn mini-btn-danger"
          @click="deleteEditingZone"
        >
          🗑️ Delete
        </button>
      </div>

      <div v-if="useGoogleMutant" class="provider-badge">
        Google Maps imagery · Leaflet editing controls remain active
      </div>

      <!-- Leaflet Map -->
      <l-map
        :zoom="zoom"
        :center="centerLatLng"
        :use-global-leaflet="useGlobalLeaflet"
        :options="leafletOptions"
        style="height: 100%; width: 100%"
        @click="onMapClick"
        ref="mapRef"
      >
        <!-- Dynamic tiles based on provider/style -->
        <l-tile-layer
          v-if="showTiles && tileLayerConfig && !googleLayerActive"
          :url="tileLayerConfig.url"
          :attribution="tileLayerConfig.attribution"
          :subdomains="tileLayerConfig.subdomains"
          :max-zoom="tileLayerConfig.maxZoom"
        />
        <l-tile-layer
          v-if="showTiles && tileLayerConfig?.overlay && !googleLayerActive"
          :url="tileLayerConfig.overlay.url"
          :attribution="tileLayerConfig.overlay.attribution || tileLayerConfig.attribution"
          :subdomains="tileLayerConfig.overlay.subdomains"
          :max-zoom="tileLayerConfig.overlay.maxZoom"
          :options="{ zIndex: 5 }"
        />

        <!-- Existing boundary polygon -->
        <l-polygon
          v-if="boundaryPolygon.length > 0"
          :lat-lngs="boundaryPolygon"
          :color="'#00FF92'"
          :weight="3"
          :fill="true"
          :fill-opacity="0.1"
          :interactive="mode === 'view'"
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
          :interactive="mode === 'view'"
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
          :interactive="mode === 'view'"
          @click="() => onMowingClick(zone.id)"
        />

        <!-- In-progress polygon (only for polygon edit modes) -->
        <l-polygon
          v-if="currentPolygonLatLng.length > 0 && (mode === 'boundary' || mode === 'exclusion' || mode === 'mowing')"
          :lat-lngs="currentPolygonLatLng"
          :color="mode === 'boundary' ? '#00FF92' : '#ffb703'"
          :weight="2"
          :fill="false"
          :dash-array="'4 4'"
        />

        <!-- Vertex handles for editing current polygon (hidden in marker mode) -->
        <l-marker
          v-for="(pt, idx) in currentPolygon"
          v-if="mode === 'boundary' || mode === 'exclusion' || mode === 'mowing'"
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
          :icon="markerDivIcon(m)"
          :draggable="mode === 'marker'"
          @moveend="(e:any) => onMarkerMoveEnd(m.marker_id, e)"
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
import { useToastStore } from '@/stores/toast';
import { shouldUseGoogleProvider, getOsmTileLayer, type TileLayerConfig } from '@/utils/mapProviders';

const mapStore = useMapStore();
const toast = useToastStore();

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

// Dynamic Leaflet tile layer when NOT using Google Mutant
const tileLayerConfig = computed<TileLayerConfig | null>(() => {
  if (props.mapProvider === 'none') return null;
  if (useGoogleMutant.value) return null;
  if (props.mapProvider === 'osm') {
    return getOsmTileLayer(props.mapStyle);
  }
  // Google provider without a usable API key falls back to a basic OSM layer for editing
  return getOsmTileLayer('standard');
});

const useGoogleMutant = computed(() => shouldUseGoogleProvider(
  props.mapProvider,
  props.googleApiKey,
  typeof window !== 'undefined' ? window.location : null
));
let googleBaseLayer: any = null;
const googleLayerActive = ref(false);

// When using Google Mutant, prefer global Leaflet to allow plugin to attach to window.L
const useGlobalLeaflet = computed(() => useGoogleMutant.value);
const leafletOptions = computed(() => ({ attributionControl: !useGoogleMutant.value }));

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
    console.warn('Google Maps JS API failed to load. Falling back to standard tiles.', e)
    googleLayerActive.value = false
    return
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
const snapToBoundary = ref(false);

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

const isPolygonMode = computed(() => mode.value === 'boundary' || mode.value === 'exclusion' || mode.value === 'mowing');
const showPolygonToolbar = computed(() => isPolygonMode.value && currentPolygon.value.length > 0 && !props.pickForPin);
const canUndoVertex = computed(() => currentPolygon.value.length > 0);
const canClosePolygon = computed(() => isPolygonMode.value && currentPolygon.value.length >= 3 && !currentPolygonClosed.value);
const canDeleteCurrent = computed(() => Boolean(editingZoneId.value) && (mode.value === 'mowing' || mode.value === 'exclusion'));

// Methods
function markerDivIcon(m: any) {
  const emoji = m.marker_type === 'home' ? '🏠' : m.marker_type === 'am_sun' ? '☀️' : m.marker_type === 'pm_sun' ? '🌅' : '📍'
  const cls = `lb-marker ${m.marker_type}`
  return L.divIcon({
    className: cls,
    html: `<span>${emoji}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  })
}

function setMode(newMode: 'view' | 'boundary' | 'exclusion' | 'mowing' | 'marker') {
  mapStore.setEditMode(newMode);
  currentPolygon.value = [];
  currentPolygonClosed.value = false;
  editingZoneId.value = null;
}

function clearCurrent() {
  currentPolygon.value = [];
  hasUnsavedChanges.value = false;
  currentPolygonClosed.value = false;
  editingZoneId.value = null;
}

function undoLastVertex() {
  if (currentPolygon.value.length === 0) return;
  const next = currentPolygon.value.slice(0, -1);
  currentPolygon.value = next;
  currentPolygonClosed.value = false;
  hasUnsavedChanges.value = next.length > 0;
}

function closePolygonManually() {
  if (!isPolygonMode.value || currentPolygon.value.length < 3) return;
  currentPolygonClosed.value = true;
  hasUnsavedChanges.value = true;
}

async function deleteEditingZone() {
  if (!editingZoneId.value) return;
  const zoneId = editingZoneId.value;
  try {
    if (mode.value === 'mowing') {
      if (!confirm('Delete this mowing zone?')) return;
      mapStore.removeMowingZone(zoneId);
    } else if (mode.value === 'exclusion') {
      if (!confirm('Delete this exclusion zone?')) return;
      mapStore.removeExclusionZone(zoneId);
    } else {
      return;
    }

    await mapStore.saveConfiguration();
    toast.show('Zone deleted', 'success', 2000);
    currentPolygon.value = [];
    currentPolygonClosed.value = false;
    editingZoneId.value = null;
    hasUnsavedChanges.value = false;
    mapStore.setEditMode('view');
  } catch (err: any) {
    const msg = err?.message || 'Failed to delete zone';
    toast.show(msg, 'error', 3000);
  }
}

async function saveChanges() {
  error.value = null;
  successMessage.value = null;
  
  try {
    // If we're in marker mode, just persist the current configuration (markers are already in the store)
    if (mode.value === 'marker') {
      await mapStore.saveConfiguration();
      successMessage.value = 'Markers saved';
      toast.show('Marker(s) saved', 'success', 2000)
      hasUnsavedChanges.value = false;
      setTimeout(() => { successMessage.value = null }, 2000)
      return;
    }

    const ready = currentPolygon.value.length >= 3 || currentPolygonClosed.value;
    if (!ready) throw new Error('Polygon needs at least 3 points');

    let clippedNotice = false;

    if (editingZoneId.value) {
      const result = clipPolygonForMode(mode.value, currentPolygon.value);
      if (result.collapsed) {
        throw new Error('Clipped zone collapsed; adjust points to stay within boundary');
      }
      mapStore.updateZonePolygon(editingZoneId.value, result.polygon);
      clippedNotice = result.clipped;
    } else if (mode.value === 'boundary') {
      const polygonCopy = clonePolygon(currentPolygon.value);
      mapStore.setBoundaryZone({
        id: mapStore.configuration?.boundary_zone?.id || `boundary_${Date.now()}`,
        name: 'Mowing Boundary',
        zone_type: 'boundary',
        polygon: polygonCopy,
        priority: 10,
        enabled: true
      });
    } else if (mode.value === 'exclusion') {
      const polygonCopy = clonePolygon(currentPolygon.value);
      mapStore.addExclusionZone({
        id: `exclusion_${Date.now()}`,
        name: 'Exclusion Zone',
        zone_type: 'exclusion_zone',
        polygon: polygonCopy,
        priority: 5,
        enabled: true,
        exclusion_zone: true
      });
    } else if (mode.value === 'mowing') {
      const result = clipPolygonForMode('mowing', currentPolygon.value);
      if (result.collapsed) {
        throw new Error('Mowing zone collapsed after clipping; adjust points and try again');
      }
      mapStore.addMowingZone({
        id: `mow_${Date.now()}`,
        name: 'Mowing Zone',
        zone_type: 'mow_zone',
        polygon: result.polygon,
        priority: 3,
        enabled: true,
        exclusion_zone: false
      });
      clippedNotice = result.clipped;
    }

    await mapStore.saveConfiguration();
    if (clippedNotice) {
      toast.show('Mowing zone clipped to boundary', 'warning', 2800);
    }
    
    successMessage.value = 'Changes saved successfully';
    toast.show('Map saved successfully', 'success', 2500)
    hasUnsavedChanges.value = false;
    currentPolygon.value = [];
    currentPolygonClosed.value = false;
    editingZoneId.value = null;
    
    setTimeout(() => {
      successMessage.value = null;
    }, 3000);
  } catch (e: any) {
    error.value = mapStore.error || e?.message || 'Failed to save changes';
    toast.show(error.value, 'error', 4000)
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
      let pt: Point = { latitude: latlng.lat, longitude: latlng.lng };
      if (snapToBoundary.value && mode.value !== 'boundary') {
        const snapped = snapPointToBoundary(pt);
        if (snapped) pt = snapped;
      }
      currentPolygon.value.push(pt);
      hasUnsavedChanges.value = true;
    }
  } else if (mode.value === 'marker') {
    mapStore.addMarker(markerType.value, { latitude: latlng.lat, longitude: latlng.lng });
    hasUnsavedChanges.value = true;
    toast.show(`${markerType.value.replace('_',' ').toUpperCase()} marker placed`, 'info', 1800)
  }
}

function onVertexMoveEnd(idx: number, e: any) {
  try {
    const ll = e?.target?.getLatLng?.();
    if (!ll) return;
    let pt: Point = { latitude: ll.lat, longitude: ll.lng };
    if (snapToBoundary.value && mode.value !== 'boundary') {
      const snapped = snapPointToBoundary(pt);
      if (snapped) pt = snapped;
    }
    const updated = [...currentPolygon.value];
    updated[idx] = pt;
    currentPolygon.value = updated;
    hasUnsavedChanges.value = true;
  } catch {
    // ignore
  }
}

function onMarkerMoveEnd(markerId: string, e: any) {
  try {
    const ll = e?.target?.getLatLng?.()
    if (!ll) return
    mapStore.updateMarker(markerId, { position: { latitude: ll.lat, longitude: ll.lng } } as any)
    hasUnsavedChanges.value = true
  } catch {/* ignore */}
}

function onBoundaryClick() {
  if (mode.value !== 'view') return;
  const bz = mapStore.configuration?.boundary_zone;
  if (!bz) return;
  currentPolygon.value = clonePolygon(bz.polygon);
  editingZoneId.value = bz.id;
  currentPolygonClosed.value = true;
  hasUnsavedChanges.value = false;
  mapStore.setEditMode('boundary');
}

function onExclusionClick(zoneId: string) {
  if (mode.value !== 'view') return;
  const z = (mapStore.configuration?.exclusion_zones || []).find(z => z.id === zoneId);
  if (!z) return;
  currentPolygon.value = clonePolygon(z.polygon);
  editingZoneId.value = z.id;
  currentPolygonClosed.value = true;
  hasUnsavedChanges.value = false;
  mapStore.setEditMode('exclusion');
}

function onMowingClick(zoneId: string) {
  if (mode.value !== 'view') return;
  const z = (mapStore.configuration?.mowing_zones || []).find(z => z.id === zoneId);
  if (!z) return;
  currentPolygon.value = clonePolygon(z.polygon);
  editingZoneId.value = z.id;
  currentPolygonClosed.value = true;
  hasUnsavedChanges.value = false;
  mapStore.setEditMode('mowing');
}

// External controls for "Edit on map" from parent
function focusMarker(markerId: string) {
  const m = (mapStore.configuration?.markers || []).find(mm => mm.marker_id === markerId)
  if (!m) return
  centerLatLng.value = [m.position.latitude, m.position.longitude]
  mapStore.setEditMode('marker')
}

function editZoneOnMap(zoneId: string, type: 'mowing' | 'exclusion' | 'boundary' = 'mowing') {
  if (type === 'boundary' && mapStore.configuration?.boundary_zone) {
    const bz = mapStore.configuration.boundary_zone
    currentPolygon.value = clonePolygon(bz.polygon)
    editingZoneId.value = bz.id
    mapStore.setEditMode('boundary')
    centerLatLng.value = [currentPolygon.value[0].latitude, currentPolygon.value[0].longitude]
    currentPolygonClosed.value = true
    hasUnsavedChanges.value = false
    return
  }
  if (type === 'exclusion') {
    const z = (mapStore.configuration?.exclusion_zones || []).find(z => z.id === zoneId)
    if (!z) return
    currentPolygon.value = clonePolygon(z.polygon)
    editingZoneId.value = z.id
    mapStore.setEditMode('exclusion')
    centerLatLng.value = [currentPolygon.value[0].latitude, currentPolygon.value[0].longitude]
    currentPolygonClosed.value = true
    hasUnsavedChanges.value = false
    return
  }
  // default mowing
  const z = (mapStore.configuration?.mowing_zones || []).find(z => z.id === zoneId)
  if (!z) return
  currentPolygon.value = clonePolygon(z.polygon)
  editingZoneId.value = z.id
  mapStore.setEditMode('mowing')
  centerLatLng.value = [currentPolygon.value[0].latitude, currentPolygon.value[0].longitude]
  currentPolygonClosed.value = true
  hasUnsavedChanges.value = false
}

defineExpose({ focusMarker, editZoneOnMap })

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

type ClipResult = {
  polygon: Point[];
  clipped: boolean;
  collapsed: boolean;
};

const COORD_EPS = 1e-9;

function clonePoint(p: Point): Point {
  return { latitude: p.latitude, longitude: p.longitude, altitude: p.altitude };
}

function clonePolygon(poly: Point[]): Point[] {
  return poly.map(clonePoint);
}

function polygonsDiffer(a: Point[], b: Point[], epsilon = 1e-9): boolean {
  if (a.length !== b.length) return true;
  for (let i = 0; i < a.length; i++) {
    if (Math.abs(a[i].latitude - b[i].latitude) > epsilon || Math.abs(a[i].longitude - b[i].longitude) > epsilon) {
      return true;
    }
  }
  return false;
}

function signedArea(points: Point[]): number {
  if (points.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const p1 = points[i];
    const p2 = points[(i + 1) % points.length];
    area += (p1.longitude * p2.latitude) - (p2.longitude * p1.latitude);
  }
  return area / 2;
}

function normalizeRing(points: Point[]): Point[] {
  if (!points.length) return [];
  const ring = clonePolygon(points);
  if (ring.length > 1) {
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (Math.abs(first.latitude - last.latitude) <= COORD_EPS && Math.abs(first.longitude - last.longitude) <= COORD_EPS) {
      ring.pop();
    }
  }
  return ring;
}

function stripClosingPoint(points: Point[]): Point[] {
  if (points.length > 1) {
    const first = points[0];
    const last = points[points.length - 1];
    if (Math.abs(first.latitude - last.latitude) <= COORD_EPS && Math.abs(first.longitude - last.longitude) <= COORD_EPS) {
      return points.slice(0, -1);
    }
  }
  return points;
}

function pointsEqual(a: Point, b: Point, epsilon = COORD_EPS): boolean {
  return Math.abs(a.latitude - b.latitude) <= epsilon && Math.abs(a.longitude - b.longitude) <= epsilon;
}

function isInsideEdge(a: Point, b: Point, p: Point, clipCCW: boolean): boolean {
  const val = isLeft(a, b, p);
  if (Math.abs(val) <= COORD_EPS) return true;
  return clipCCW ? val >= 0 : val <= 0;
}

function clipPolygonForMode(currentMode: string, poly: Point[]): ClipResult {
  const original = clonePolygon(poly);
  if (currentMode !== 'mowing') {
    return { polygon: original, clipped: false, collapsed: false };
  }
  const boundary = mapStore.configuration?.boundary_zone?.polygon;
  if (!boundary || boundary.length < 3) {
    return { polygon: original, clipped: false, collapsed: false };
  }
  const clipped = polygonClip(boundary, original);
  const cleaned = stripClosingPoint(clipped);
  if (cleaned.length < 3) {
    return { polygon: original, clipped: false, collapsed: true };
  }
  const clippedClone = clonePolygon(cleaned);
  return {
    polygon: clippedClone,
    clipped: polygonsDiffer(original, clippedClone),
    collapsed: false
  };
}

// Helper: polygon clip subject by clipper (both arrays of {latitude, longitude})
function polygonClip(clipper: Point[], subject: Point[]): Point[] {
  if (!clipper.length || !subject.length) return clonePolygon(subject);
  const clipRing = normalizeRing(clipper);
  if (clipRing.length < 3) return clonePolygon(subject);

  let output = clonePolygon(subject);
  const clipCCW = signedArea(clipRing) >= 0;

  for (let i = 0; i < clipRing.length; i++) {
    const A = clipRing[i];
    const B = clipRing[(i + 1) % clipRing.length];
    if (pointsEqual(A, B)) continue;

    const input = output.slice();
    output = [];
    if (!input.length) break;

    for (let j = 0; j < input.length; j++) {
      const P = input[j];
      const Q = input[(j + 1) % input.length];
      const P_in = isInsideEdge(A, B, P, clipCCW);
      const Q_in = isInsideEdge(A, B, Q, clipCCW);

      if (P_in && Q_in) {
        output.push(clonePoint(Q));
      } else if (P_in && !Q_in) {
        output.push(intersection(A, B, P, Q));
      } else if (!P_in && Q_in) {
        output.push(intersection(A, B, P, Q));
        output.push(clonePoint(Q));
      }
    }
  }

  return output;
}

function isLeft(a: Point, b: Point, c: Point) {
  return (b.longitude - a.longitude) * (c.latitude - a.latitude) - (b.latitude - a.latitude) * (c.longitude - a.longitude);
}

function intersection(a: Point, b: Point, p: Point, q: Point): Point {
  const x1 = a.longitude, y1 = a.latitude;
  const x2 = b.longitude, y2 = b.latitude;
  const x3 = p.longitude, y3 = p.latitude;
  const x4 = q.longitude, y4 = q.latitude;
  const den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (Math.abs(den) < 1e-12) {
    return clonePoint(q);
  }
  const xi = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den;
  const yi = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den;
  return { latitude: yi, longitude: xi };
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

// Snapping helpers
function snapPointToBoundary(p: Point): Point | null {
  const boundary = mapStore.configuration?.boundary_zone?.polygon;
  if (!boundary || boundary.length < 2) return null;
  let best: { pt: Point; d2: number } | null = null;
  for (let i = 0; i < boundary.length; i++) {
    const a = boundary[i];
    const b = boundary[(i + 1) % boundary.length];
    const proj = projectPointToSegment(p, a, b);
    const d2 = (proj.latitude - p.latitude) ** 2 + (proj.longitude - p.longitude) ** 2;
    if (!best || d2 < best.d2) best = { pt: proj, d2 };
  }
  return best?.pt || null;
}

function projectPointToSegment(p: Point, a: Point, b: Point): Point {
  const ax = a.longitude, ay = a.latitude;
  const bx = b.longitude, by = b.latitude;
  const px = p.longitude, py = p.latitude;
  const vx = bx - ax, vy = by - ay;
  const len2 = vx * vx + vy * vy;
  if (len2 < 1e-12) return a;
  let t = ((px - ax) * vx + (py - ay) * vy) / len2;
  t = Math.max(0, Math.min(1, t));
  return { latitude: ay + t * vy, longitude: ax + t * vx };
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

.floating-toolbar {
  position: absolute;
  top: 1rem;
  right: 1rem;
  display: flex;
  gap: 0.5rem;
  background: rgba(0, 0, 0, 0.75);
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  z-index: 210;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.provider-badge {
  position: absolute;
  bottom: 1rem;
  left: 1rem;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  padding: 0.4rem 0.75rem;
  border-radius: 4px;
  font-size: 0.78rem;
  letter-spacing: 0.01em;
  pointer-events: none;
  z-index: 205;
  backdrop-filter: blur(2px);
}

.mini-btn {
  background: var(--primary-light);
  border: none;
  color: var(--text-color);
  font-size: 0.75rem;
  padding: 0.35rem 0.65rem;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.mini-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.mini-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mini-btn-danger {
  background: #ff4343;
  color: #fff;
}

.cursor-crosshair { cursor: crosshair; }
.cursor-pin { cursor: copy; }

/* Ensure the Leaflet container fills the canvas */
.editor-canvas :deep(.leaflet-container) {
  width: 100%;
  height: 100%;
  pointer-events: auto;
}

.editor-canvas.google-active :deep(.leaflet-control-attribution) {
  display: none;
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

.unsaved-badge {
  display: inline-flex;
  align-items: center;
  gap: .25rem;
  padding: .25rem .5rem;
  border-radius: 999px;
  background: rgba(255,200,0,0.15);
  color: #ffd166;
  font-weight: 700;
  margin-left: .5rem;
}

/* Emoji divIcon styling for map markers */
:deep(.lb-marker) {
  display: grid;
  place-items: center;
  width: 28px; height: 28px;
  border-radius: 50%;
  background: rgba(0,0,0,0.7);
  border: 2px solid rgba(255,255,255,0.8);
  color: #fff;
  font-size: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
:deep(.lb-marker.home) { border-color: #00ff92; }
:deep(.lb-marker.am_sun) { border-color: #ffd166; }
:deep(.lb-marker.pm_sun) { border-color: #ffa3ff; }
:deep(.lb-marker.custom) { border-color: #66d9ff; }

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

@media (prefers-reduced-motion: reduce) {
  .btn { transition: none !important; }
}
</style>

<template>
  <div class="mission-planner-view">
    <h1>Mission Planner</h1>
    <div class="map-toolbar">
      <label class="follow-toggle"><input type="checkbox" v-model="followMower" /> Follow mower</label>
      <label class="map-style-toggle">
        Map style
        <select v-model="mapStyle" @change="handleMapStyleChange">
          <option value="standard">Standard</option>
          <option value="satellite">Satellite</option>
          <option value="hybrid">Hybrid</option>
          <option value="terrain">Terrain</option>
        </select>
      </label>
      <button class="btn" @click="recenterToMower" :disabled="!mowerLatLng">🎯 Recenter</button>
      <button class="btn" @click="undoLastWaypoint" :disabled="missionStore.waypoints.length === 0">↩️ Undo last</button>
      <button class="btn btn-danger" @click="clearAllWaypoints" :disabled="missionStore.waypoints.length === 0">🗑️ Clear all</button>
      <button
        class="btn"
        :class="calibratingGps ? 'btn-warning btn-pulse' : 'btn-secondary'"
        @click="toggleGpsCalibration"
        :title="calibratingGps ? 'Click on the map where the mower is actually located' : 'Align displayed GPS position with satellite imagery'"
      >{{ calibratingGps ? '📍 Click mower location…' : '📍 Calibrate GPS' }}</button>
      <button v-if="gpsOffsetActive" class="btn btn-secondary" @click="clearGpsCalibration" title="Remove GPS offset and return to raw GPS coordinates">✖ Clear GPS offset</button>
    </div>
    <div class="map-container">
      <MissionMap
        ref="missionMapRef"
        :waypoints="missionStore.waypoints"
        :mowerPosition="mowerPosition"
        :followMower="followMower"
        :mapSettings="mapDisplaySettings"
        @add-waypoint="handleAddWaypoint"
        @update-waypoint="handleUpdateWaypoint"
        @remove-waypoint="handleRemoveWaypoint"
      />
    </div>
    <MissionWaypointList />
    <div class="mission-controls">
      <input v-model="missionName" placeholder="Mission Name" />
      <button @click="createMission" :disabled="creatingMission || !missionName || missionStore.waypoints.length === 0">
        {{ creatingMission ? 'Creating…' : 'Create Mission' }}
      </button>
      <button @click="startMission" :disabled="startingMission || !missionStore.currentMission">
        {{ startingMission ? 'Starting…' : 'Start Mission' }}
      </button>
      <button @click="pauseMission" :disabled="missionStore.missionStatus !== 'running'">Pause</button>
      <button @click="resumeMission" :disabled="missionStore.missionStatus !== 'paused'">Resume</button>
      <button @click="abortMission" :disabled="!missionStore.currentMission">Abort</button>
    </div>
    <p v-if="missionActionHint" class="mission-action-hint">{{ missionActionHint }}</p>
    <div v-if="missionStore.currentMission" class="mission-status-panel">
      <h2>
        Mission Status:
        <span class="mission-status-pill" :class="`mission-status-pill--${missionStatusTone}`">
          {{ missionStatusLabel }}
        </span>
      </h2>
      <p>Progress: {{ missionStore.progress.toFixed(2) }}%</p>
      <p>Waypoint: {{ missionWaypointProgress }}</p>
      <p v-if="missionStore.statusDetail" class="mission-status-detail">
        {{ missionStore.statusDetail }}
      </p>
      <p v-if="missionStore.isRecoveredPause" class="mission-status-hint">
        Review mower state before resuming — this mission was recovered conservatively after a backend restart.
      </p>
    </div>
  </div>
  
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import MissionWaypointList from '@/components/MissionWaypointList.vue';
import MissionMap from '@/components/mission/MissionMap.vue';
import { useMissionStore, type MissionLifecycleStatus, type Waypoint } from '@/stores/mission';
import { useMapStore } from '@/stores/map';
import { useToastStore } from '@/stores/toast';
import { useApiService } from '@/services/api';
import { useWebSocket } from '@/services/websocket';

const missionStore = useMissionStore();
const mapStore = useMapStore();
const toast = useToastStore();
const api = useApiService();
const telemetrySocket = useWebSocket('telemetry');

const missionMapRef = ref<any>(null);
const followMower = ref(true);
const mowerLatLng = ref<[number, number] | null>(null);
const gpsAccuracyMeters = ref<number | null>(null);
const mowerHeading = ref<number | null>(null);
const missionName = ref('');
const mapStyle = ref<'standard' | 'satellite' | 'hybrid' | 'terrain'>('standard');
const creatingMission = ref(false);
const startingMission = ref(false);
const missionActionHint = ref('');
const calibratingGps = ref(false);
const gpsOffsetActive = ref(false);
const mapDisplaySettings = ref<{ provider: 'google' | 'osm' | 'none'; style: 'standard' | 'satellite' | 'hybrid' | 'terrain'; google_api_key: string }>({
  provider: 'osm',
  style: 'standard',
  google_api_key: '',
});
const restPollTimer = ref<number | null>(null);
const lastWsUpdateAt = ref<number>(0);

let navigationHandler: ((payload: any) => void) | null = null;
let componentDestroyed = false;

onMounted(async () => {
  componentDestroyed = false;

  try {
    const response = await api.get('/api/v2/settings/maps');
    const payload = response?.data && typeof response.data === 'object' ? response.data : {};
    const missionPlannerSettings = payload.mission_planner && typeof payload.mission_planner === 'object'
      ? payload.mission_planner
      : payload;
    mapDisplaySettings.value = {
      provider: missionPlannerSettings.provider === 'google' || missionPlannerSettings.provider === 'none' ? missionPlannerSettings.provider : 'osm',
      style: ['standard', 'satellite', 'hybrid', 'terrain'].includes(String(missionPlannerSettings.style)) ? missionPlannerSettings.style : 'standard',
      google_api_key: typeof payload.google_api_key === 'string' ? payload.google_api_key : '',
    };
    mapStyle.value = mapDisplaySettings.value.style;
  } catch (error) {
    console.warn('Failed to load mission planner map display settings:', error);
  }

  // Load current GPS calibration offset (so "Clear GPS offset" shows if one is active)
  try {
    const offsetRes = await api.get('/api/v2/gps/offset');
    const d = offsetRes?.data || {};
    gpsOffsetActive.value = !!(d.offset_lat_m || d.offset_lon_m);
  } catch {/* ignore — endpoint may not exist yet on first load */}

  // Ensure configuration for initial center
  if (!mapStore.configuration) {
    try {
      await mapStore.loadConfiguration('default');
    } catch (error) {
      console.error('Failed to load map configuration on mount:', error);
    }
  }

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
        lastWsUpdateAt.value = Date.now();
      }
      const hdg = payload?.nav_heading;
      mowerHeading.value = hdg != null && Number.isFinite(Number(hdg)) ? Number(hdg) : null;
    };
    telemetrySocket.subscribe('telemetry.navigation', navigationHandler);
  } catch (error) {
    console.warn('Failed to initialize telemetry socket for mission planner:', error);
  }

  // REST fallback polling for environments that block WebSockets (e.g., some Cloudflare setups)
  restPollTimer.value = window.setInterval(async () => {
    try {
      // If we have not received a websocket update within 5 seconds, poll REST
      if (Date.now() - lastWsUpdateAt.value < 5000) return;
      const res = await fetch('/api/v2/dashboard/telemetry', { headers: { 'Cache-Control': 'no-cache' } })
      if (!res.ok) return
      const data = await res.json()
      const lat = Number(data?.position?.latitude)
      const lon = Number(data?.position?.longitude)
      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        mowerLatLng.value = [lat, lon]
        const acc = Number(data?.position?.accuracy)
        gpsAccuracyMeters.value = Number.isFinite(acc) ? acc : null
        const hdg = data?.nav_heading
        mowerHeading.value = hdg != null && Number.isFinite(Number(hdg)) ? Number(hdg) : null
      }
    } catch {/* ignore */}
  }, 2000)
});

onUnmounted(() => {
  componentDestroyed = true;

  if (navigationHandler) {
    telemetrySocket.unsubscribe('telemetry.navigation', navigationHandler);
    navigationHandler = null;
  }

  if (restPollTimer.value) {
    clearInterval(restPollTimer.value)
    restPollTimer.value = null
  }
});

const mowerPosition = computed(() => {
  if (!mowerLatLng.value) return null;
  return {
    lat: mowerLatLng.value[0],
    lon: mowerLatLng.value[1],
    accuracy: gpsAccuracyMeters.value || 0,
    heading: mowerHeading.value,
  };
});

function handleAddWaypoint(lat: number, lon: number) {
  if (calibratingGps.value) {
    submitGpsCalibration(lat, lon);
    return;
  }
  missionStore.addWaypoint(lat, lon);
}

function handleUpdateWaypoint(waypoint: Waypoint) {
  missionStore.updateWaypoint(waypoint);
}

function handleRemoveWaypoint(id: string) {
  missionStore.removeWaypoint(id);
}

function recenterToMower() {
  if (mowerLatLng.value && missionMapRef.value) {
    missionMapRef.value.recenter(mowerLatLng.value[0], mowerLatLng.value[1], 18);
  }
}

function toggleGpsCalibration() {
  calibratingGps.value = !calibratingGps.value;
  if (calibratingGps.value) {
    missionActionHint.value = '📍 Click on the satellite map where the mower is physically located to align GPS. Press the button again to cancel.';
  } else {
    missionActionHint.value = '';
  }
}

async function submitGpsCalibration(lat: number, lon: number) {
  calibratingGps.value = false;
  missionActionHint.value = 'Saving GPS calibration…';
  try {
    const res = await api.post('/api/v2/gps/calibrate', { latitude: lat, longitude: lon });
    const d = res?.data || {};
    gpsOffsetActive.value = true;
    missionActionHint.value = `✅ GPS offset saved: ${(d.offset_lat_m ?? 0).toFixed(2)} m north, ${(d.offset_lon_m ?? 0).toFixed(2)} m east. Displayed position now matches imagery.`;
    setTimeout(() => { if (missionActionHint.value.startsWith('✅ GPS')) missionActionHint.value = ''; }, 8000);
  } catch (err: any) {
    const msg = err?.response?.data?.detail || String(err);
    missionActionHint.value = `❌ GPS calibration failed: ${msg}`;
    setTimeout(() => { if (missionActionHint.value.startsWith('❌')) missionActionHint.value = ''; }, 8000);
  }
}

async function clearGpsCalibration() {
  try {
    await api.delete('/api/v2/gps/offset');
    gpsOffsetActive.value = false;
    missionActionHint.value = '✅ GPS offset cleared — using raw GPS coordinates.';
    setTimeout(() => { if (missionActionHint.value.startsWith('✅ GPS offset cleared')) missionActionHint.value = ''; }, 5000);
  } catch (err: any) {
    const msg = err?.response?.data?.detail || String(err);
    missionActionHint.value = `❌ Failed to clear GPS offset: ${msg}`;
    setTimeout(() => { if (missionActionHint.value.startsWith('❌')) missionActionHint.value = ''; }, 5000);
  }
}

async function handleMapStyleChange() {
  const nextSettings = {
    ...mapDisplaySettings.value,
    style: mapStyle.value,
  };
  mapDisplaySettings.value = nextSettings;
  try {
    await api.put('/api/v2/settings/maps', {
      mission_planner: {
        provider: nextSettings.provider,
        style: nextSettings.style,
      },
    });
  } catch (error) {
    console.warn('Failed to persist mission planner map style preference:', error);
    toast.show('Failed to save mission planner map preference', 'warning', 4000);
  }
}

const createMission = async () => {
  if (!missionName.value) {
    return;
  }

  creatingMission.value = true;
  try {
    await missionStore.createMission(missionName.value);
    missionActionHint.value = 'Mission created. Press Start Mission to send it to the mower.';
    toast.show('Mission created. Press Start Mission when you are ready.', 'success', 3500);
  } catch (error) {
    console.error('Mission creation failed:', error);
    missionActionHint.value = missionStore.statusDetail || 'Mission creation failed.';
    toast.show(missionActionHint.value, 'error', 5000);
  } finally {
    creatingMission.value = false;
  }
};

function clearAllWaypoints() {
  if (missionStore.waypoints.length && confirm('Clear all waypoints from this mission plan?')) {
    missionStore.clearWaypoints();
  }
}

function undoLastWaypoint() {
  missionStore.removeLastWaypoint();
}

const startMission = async () => {
  startingMission.value = true;
  try {
    await missionStore.startCurrentMission();
    missionActionHint.value = 'Mission start accepted. Watch the status panel for progress and safety feedback.';
    toast.show('Mission start accepted', 'success', 3000);
  } catch (error) {
    console.error('Mission start failed:', error);
    missionActionHint.value = missionStore.statusDetail || 'Mission start failed.';
    toast.show(missionActionHint.value, 'error', 5000);
  } finally {
    startingMission.value = false;
  }
};
const pauseMission = async () => {
  try {
    await missionStore.pauseCurrentMission();
    missionActionHint.value = 'Mission paused.';
    toast.show('Mission paused', 'info', 2500);
  } catch (error) {
    console.error('Mission pause failed:', error);
    missionActionHint.value = missionStore.statusDetail || 'Mission pause failed.';
    toast.show(missionActionHint.value, 'error', 5000);
  }
};
const resumeMission = async () => {
  try {
    await missionStore.resumeCurrentMission();
    missionActionHint.value = 'Mission resumed.';
    toast.show('Mission resumed', 'success', 2500);
  } catch (error) {
    console.error('Mission resume failed:', error);
    missionActionHint.value = missionStore.statusDetail || 'Mission resume failed.';
    toast.show(missionActionHint.value, 'error', 5000);
  }
};
const abortMission = async () => {
  try {
    await missionStore.abortCurrentMission();
    missionActionHint.value = 'Mission aborted.';
    toast.show('Mission aborted', 'warning', 3000);
  } catch (error) {
    console.error('Mission abort failed:', error);
    missionActionHint.value = missionStore.statusDetail || 'Mission abort failed.';
    toast.show(missionActionHint.value, 'error', 5000);
  }
};

const missionStatusLabel = computed(() => {
  switch (missionStore.missionStatus) {
    case 'idle':
      return 'Idle';
    case 'running':
      return 'Running';
    case 'paused':
      return missionStore.isRecoveredPause ? 'Paused (recovered)' : 'Paused';
    case 'completed':
      return 'Completed';
    case 'aborted':
      return 'Aborted';
    case 'failed':
      return 'Failed';
    default:
      return 'Unknown';
  }
});

const missionStatusTone = computed(() => {
  const status = missionStore.missionStatus as MissionLifecycleStatus;
  return status || 'idle';
});

const missionWaypointProgress = computed(() => {
  const total = missionStore.totalWaypoints || missionStore.currentMission?.waypoints.length || 0;
  if (!total) {
    return 'No waypoints yet';
  }

  const currentIndex = missionStore.currentWaypointIndex ?? 0;
  return `${Math.min(currentIndex + 1, total)} of ${total}`;
});

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
  background: #1a1a1a; /* Dark background for loading state */
}
.mission-controls {
  display: flex;
  gap: 1rem;
  align-items: center;
}
.mission-status-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}
.mission-status-pill {
  display: inline-flex;
  margin-left: 0.5rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.mission-status-pill--idle,
.mission-status-pill--paused {
  background: rgba(246, 199, 95, 0.18);
  color: #f6c75f;
}
.mission-status-pill--running,
.mission-status-pill--completed {
  background: rgba(0, 255, 146, 0.14);
  color: var(--accent-green);
}
.mission-status-pill--aborted,
.mission-status-pill--failed {
  background: rgba(255, 107, 107, 0.14);
  color: #ff6b6b;
}
.mission-status-detail {
  color: rgba(255, 255, 255, 0.82);
}
.mission-status-hint {
  color: #f6c75f;
  font-weight: 600;
}
.mission-action-hint {
  margin: 0;
  color: rgba(255, 255, 255, 0.78);
}
.map-toolbar { display:flex; gap:1rem; align-items:center; }
.map-style-toggle { display:flex; align-items:center; gap:.5rem; }
.map-style-toggle select {
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  padding: 0.35rem 0.5rem;
}
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

/* GPS calibration button states */
.btn-secondary { background: #4b5563; border-color: #6b7280; }
.btn-secondary:hover { background: #374151; }
.btn-warning { background: #d97706; border-color: #f59e0b; color: #fff; }
.btn-warning:hover { background: #b45309; }
.btn-pulse { animation: gps-pulse 1.2s ease-in-out infinite; }
@keyframes gps-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.6); }
  50%       { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0); }
}
</style>

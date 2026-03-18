<template>
  <div class="mission-planner-view">
    <h1>Mission Planner</h1>
    <div class="map-toolbar">
      <label class="follow-toggle"><input type="checkbox" v-model="followMower" /> Follow mower</label>
      <button class="btn" @click="recenterToMower" :disabled="!mowerLatLng">🎯 Recenter</button>
      <button class="btn" @click="undoLastWaypoint" :disabled="missionStore.waypoints.length === 0">↩️ Undo last</button>
      <button class="btn btn-danger" @click="clearAllWaypoints" :disabled="missionStore.waypoints.length === 0">🗑️ Clear all</button>
    </div>
    <div class="map-container">
      <MissionMap
        ref="missionMapRef"
        :waypoints="missionStore.waypoints"
        :mowerPosition="mowerPosition"
        :followMower="followMower"
        @add-waypoint="handleAddWaypoint"
        @update-waypoint="handleUpdateWaypoint"
        @remove-waypoint="handleRemoveWaypoint"
      />
    </div>
    <MissionWaypointList />
    <div class="mission-controls">
      <input v-model="missionName" placeholder="Mission Name" />
      <button @click="createMission" :disabled="!missionName || missionStore.waypoints.length === 0">Create Mission</button>
      <button @click="startMission" :disabled="!missionStore.currentMission">Start Mission</button>
      <button @click="pauseMission" :disabled="missionStore.missionStatus !== 'running'">Pause</button>
      <button @click="resumeMission" :disabled="missionStore.missionStatus !== 'paused'">Resume</button>
      <button @click="abortMission" :disabled="!missionStore.currentMission">Abort</button>
    </div>
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
import { useApiService } from '@/services/api';
import { useWebSocket } from '@/services/websocket';

const missionStore = useMissionStore();
const mapStore = useMapStore();
const api = useApiService();
const telemetrySocket = useWebSocket('telemetry');

const missionMapRef = ref<any>(null);
const followMower = ref(true);
const mowerLatLng = ref<[number, number] | null>(null);
const gpsAccuracyMeters = ref<number | null>(null);
const missionName = ref('');
const restPollTimer = ref<number | null>(null);
const lastWsUpdateAt = ref<number>(0);

let navigationHandler: ((payload: any) => void) | null = null;
let componentDestroyed = false;

onMounted(async () => {
  componentDestroyed = false;

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
  telemetrySocket.disconnect();

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
  };
});

function handleAddWaypoint(lat: number, lon: number) {
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

const createMission = () => {
  if (missionName.value) {
    missionStore.createMission(missionName.value);
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

const startMission = () => missionStore.startCurrentMission();
const pauseMission = () => missionStore.pauseCurrentMission();
const resumeMission = () => missionStore.resumeCurrentMission();
const abortMission = () => missionStore.abortCurrentMission();

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

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import apiService from '@/services/api';
import { useWebSocket } from '@/services/websocket';

export interface Waypoint {
  id: string;
  lat: number;
  lon: number;
  blade_on: boolean;
  speed: number;
}

export interface Mission {
  id: string;
  name: string;
  waypoints: Waypoint[];
  created_at: string;
}

export type MissionLifecycleStatus = 'idle' | 'running' | 'paused' | 'completed' | 'aborted' | 'failed';

export interface MissionStatusResponse {
  mission_id: string;
  status: MissionLifecycleStatus;
  current_waypoint_index: number | null;
  completion_percentage: number;
  total_waypoints: number;
  detail?: string | null;
}

function extractMissionErrorMessage(error: unknown, fallback: string): string {
  const message = (error as {
    response?: {
      data?: {
        detail?: string;
        message?: string;
      };
    };
    message?: string;
  })?.response?.data?.detail
    || (error as {
      response?: {
        data?: {
          detail?: string;
          message?: string;
        };
      };
      message?: string;
    })?.response?.data?.message
    || (error as { message?: string })?.message;

  return String(message || fallback);
}

const CURRENT_MISSION_ID_KEY = 'lawnberry:currentMissionId';

export const useMissionStore = defineStore('mission', () => {
  const waypoints = ref<Waypoint[]>([]);
  const currentMission = ref<Mission | null>(null);
  const missionStatus = ref<MissionLifecycleStatus>('idle');
  const progress = ref(0);
  const currentWaypointIndex = ref<number | null>(null);
  const totalWaypoints = ref(0);
  const statusDetail = ref<string | null>(null);
  const pathTrace = ref<[number, number][]>([]);
  const missions = ref<Mission[]>([]);
  const isRecoveredPause = computed(() => {
    return missionStatus.value === 'paused' && /recover/i.test(statusDetail.value ?? '');
  });
  let statusPollInterval: ReturnType<typeof setInterval> | null = null;

  const _persistCurrentMissionId = (id: string | null) => {
    if (id) {
      localStorage.setItem(CURRENT_MISSION_ID_KEY, id);
    } else {
      localStorage.removeItem(CURRENT_MISSION_ID_KEY);
    }
  };

  const { subscribe, unsubscribe } = useWebSocket();

  const applyMissionStatus = (status: MissionStatusResponse) => {
    missionStatus.value = status.status;
    progress.value = status.completion_percentage;
    currentWaypointIndex.value = status.current_waypoint_index;
    totalWaypoints.value = status.total_waypoints;
    statusDetail.value = status.detail ?? null;
  };

  const addWaypoint = (lat: number, lon: number) => {
    const newWaypoint: Waypoint = {
      id: new Date().toISOString(),
      lat,
      lon,
      blade_on: false,
      speed: 50,
    };
    waypoints.value.push(newWaypoint);
  };

  const removeWaypoint = (id: string) => {
    waypoints.value = waypoints.value.filter(wp => wp.id !== id);
  };

  const updateWaypoint = (updatedWaypoint: Waypoint) => {
    const index = waypoints.value.findIndex(wp => wp.id === updatedWaypoint.id);
    if (index !== -1) {
      waypoints.value[index] = updatedWaypoint;
    }
  };

  const reorderWaypoints = (newOrder: Waypoint[]) => {
    waypoints.value = newOrder;
  };

  const removeLastWaypoint = () => {
    if (waypoints.value.length > 0) {
      waypoints.value = waypoints.value.slice(0, -1);
    }
  };

  const clearWaypoints = () => {
    waypoints.value = [];
  };

  const appendTracePoint = (lat: number, lon: number) => {
    if (missionStatus.value !== 'running') return;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const last = pathTrace.value[pathTrace.value.length - 1];
    if (last && Math.abs(last[0] - lat) < 1e-6 && Math.abs(last[1] - lon) < 1e-6) return;
    pathTrace.value.push([lat, lon]);
    if (pathTrace.value.length > 5000) pathTrace.value.shift();
  };

  const clearTrace = () => {
    pathTrace.value = [];
  };

  const _setCurrentMission = (mission: Mission) => {
    currentMission.value = mission;
    _persistCurrentMissionId(mission.id);
  };

  const selectMission = async (mission: Mission) => {
    _setCurrentMission(mission);
    waypoints.value = [...mission.waypoints];
    try {
      const response = await apiService.get<MissionStatusResponse>(`/api/v2/missions/${mission.id}/status`);
      applyMissionStatus(response.data);
    } catch {
      missionStatus.value = 'idle';
    }
  };

  const fetchMissions = async () => {
    try {
      const response = await apiService.get<Mission[]>('/api/v2/missions/list');
      missions.value = response.data;
    } catch (error) {
      console.error('Error fetching missions:', error);
    }
  };

  const updateMissionById = async (id: string, payload: { name?: string; waypoints?: Waypoint[] }) => {
    try {
      const response = await apiService.patch<Mission>(`/api/v2/missions/${id}`, payload);
      const updated = response.data;
      const idx = missions.value.findIndex(m => m.id === id);
      if (idx !== -1) {
        missions.value[idx] = updated;
      }
      if (currentMission.value?.id === id) {
        currentMission.value = updated;
        if (payload.waypoints !== undefined) {
          waypoints.value = [...updated.waypoints];
        }
      }
      return updated;
    } catch (error) {
      const msg = extractMissionErrorMessage(error, 'Unable to update mission.');
      statusDetail.value = msg;
      throw error;
    }
  };

  const deleteMissionById = async (id: string) => {
    try {
      await apiService.delete(`/api/v2/missions/${id}`);
      missions.value = missions.value.filter(m => m.id !== id);
      if (currentMission.value?.id === id) {
        currentMission.value = null;
        waypoints.value = [];
        _persistCurrentMissionId(null);
        stopStatusPolling();
        missionStatus.value = 'idle';
      }
    } catch (error) {
      const msg = extractMissionErrorMessage(error, 'Unable to delete mission.');
      statusDetail.value = msg;
      throw error;
    }
  };

  const handleMissionDeletedWsEvent = async (data: any) => {
    const payload = data?.data ?? data;
    const mission_id = payload?.mission_id;
    if (!mission_id) return;
    missions.value = missions.value.filter(m => m.id !== mission_id);
    if (currentMission.value?.id === mission_id) {
      currentMission.value = null;
      waypoints.value = [];
      _persistCurrentMissionId(null);
      stopStatusPolling();
      missionStatus.value = 'idle';
    }
  };

  const handleMissionUpdatedWsEvent = async (data: any) => {
    const payload = data?.data ?? data;
    const mission_id = payload?.mission_id;
    if (!mission_id) return;
    try {
      const response = await apiService.get<Mission>(`/api/v2/missions/${mission_id}`);
      const updated = response.data;
      const idx = missions.value.findIndex(m => m.id === mission_id);
      if (idx !== -1) {
        missions.value[idx] = updated;
      }
      if (currentMission.value?.id === mission_id) {
        currentMission.value = updated;
      }
    } catch {
      // Mission may have been deleted before we fetched it — ignore
    }
  };

  const init = async () => {
    // Always register cross-client WS listeners, regardless of saved mission state
    subscribe('mission.deleted', handleMissionDeletedWsEvent);
    subscribe('mission.updated', handleMissionUpdatedWsEvent);

    const savedId = localStorage.getItem(CURRENT_MISSION_ID_KEY);
    if (!savedId) return;
    try {
      const missionRes = await apiService.get<Mission>(`/api/v2/missions/${savedId}`);
      const statusRes = await apiService.get<MissionStatusResponse>(`/api/v2/missions/${savedId}/status`);
      currentMission.value = missionRes.data;
      waypoints.value = [...missionRes.data.waypoints];
      applyMissionStatus(statusRes.data);
      if (statusRes.data.status === 'running' || statusRes.data.status === 'paused') {
        startStatusPolling();
      }
    } catch {
      localStorage.removeItem(CURRENT_MISSION_ID_KEY);
    }
  };

  const createMission = async (name: string) => {
    try {
      const response = await apiService.post<Mission>('/api/v2/missions/create', {
        name,
        waypoints: waypoints.value,
      });
      _setCurrentMission(response.data);
      missionStatus.value = 'idle';
      progress.value = 0;
      currentWaypointIndex.value = 0;
      totalWaypoints.value = response.data.waypoints.length;
      statusDetail.value = null;
      return response.data;
    } catch (error) {
      console.error('Error creating mission:', error);
      statusDetail.value = extractMissionErrorMessage(error, 'Unable to create mission.');
      throw error;
    }
  };

  const startCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/start`, {});
      clearTrace();
      missionStatus.value = 'running';
      statusDetail.value = null;
      startStatusPolling();
    } catch (error) {
      console.error('Error starting mission:', error);
      statusDetail.value = extractMissionErrorMessage(error, 'Unable to start mission.');
      throw error;
    }
  };

  /**
   * Pauses the current mission.
   * On API failure, sets statusDetail to an error message but does NOT throw —
   * callers should watch statusDetail rather than catching rejections.
   * (Contrast with startCurrentMission / abortCurrentMission which do throw.)
   */
  const pauseCurrentMission = async (): Promise<void> => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/pause`, {});
    } catch (error) {
      console.error('Error pausing mission:', error);
      statusDetail.value = 'Failed to pause mission';
      return; // missionStatus is NOT changed — error surfaced via statusDetail
    }
    // Only reached when the API call succeeded:
    missionStatus.value = 'paused';
    statusDetail.value = 'Paused by operator';
    stopStatusPolling();
  };

  /**
   * Resumes the current mission after a pause.
   * On API failure, sets statusDetail to an error message but does NOT throw —
   * callers should watch statusDetail rather than catching rejections.
   * (Contrast with startCurrentMission / abortCurrentMission which do throw.)
   */
  const resumeCurrentMission = async (): Promise<void> => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/resume`, {});
    } catch (error) {
      console.error('Error resuming mission:', error);
      statusDetail.value = 'Failed to resume mission';
      return; // missionStatus is NOT changed — error surfaced via statusDetail
    }
    // Only reached when the API call succeeded:
    missionStatus.value = 'running';
    statusDetail.value = null;
    startStatusPolling();
  };

  const abortCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/abort`, {});
      missionStatus.value = 'aborted';
      statusDetail.value = 'Mission aborted by operator';
      stopStatusPolling();
      currentMission.value = null;
      _persistCurrentMissionId(null);
    } catch (error) {
      console.error('Error aborting mission:', error);
      statusDetail.value = extractMissionErrorMessage(error, 'Unable to abort mission.');
      throw error;
    }
  };

  const pollMissionStatus = async () => {
    if (!currentMission.value) return;
    try {
      const response = await apiService.get<MissionStatusResponse>(`/api/v2/missions/${currentMission.value.id}/status`);
      const status = response.data;
      applyMissionStatus(status);
      if (status.status === 'completed' || status.status === 'aborted' || status.status === 'failed') {
        stopStatusPolling();
      }
    } catch (error) {
      console.error('Error polling mission status:', error);
    }
  };

  const startStatusPolling = () => {
    if (statusPollInterval) return;
    // Subscribe to real-time WebSocket push events for this mission
    subscribe('mission.status', handleMissionStatusWsEvent);
    subscribe('telemetry.navigation', handleTelemetryNavWsEvent);
    // 30 s reconciliation fallback poll (replaces the previous 2 s poll)
    statusPollInterval = setInterval(pollMissionStatus, 30000);
  };

  const stopStatusPolling = () => {
    if (statusPollInterval) {
      clearInterval(statusPollInterval);
      statusPollInterval = null;
    }
    unsubscribe('mission.status', handleMissionStatusWsEvent);
    unsubscribe('telemetry.navigation', handleTelemetryNavWsEvent);
  };

  const handleTelemetryNavWsEvent = (data: any) => {
    const payload = data?.data ?? data;
    const lat = payload?.position?.latitude;
    const lon = payload?.position?.longitude;
    if (lat != null && lon != null) {
      appendTracePoint(lat, lon);
    }
  };

  const handleMissionStatusWsEvent = (data: any) => {
    // Guard: only process events for the currently tracked mission
    if (!currentMission.value) return;
    const payload = data?.data ?? data;
    if (payload?.mission_id && payload.mission_id !== currentMission.value.id) return;

    if (payload?.status) {
      missionStatus.value = payload.status as MissionLifecycleStatus;
    }
    if (payload?.progress_pct !== undefined) {
      progress.value = payload.progress_pct;
    }
    if (payload?.detail !== undefined) {
      statusDetail.value = payload.detail ?? null;
    }

    const terminal: MissionLifecycleStatus[] = ['completed', 'aborted', 'failed'];
    if (terminal.includes(missionStatus.value)) {
      stopStatusPolling();
    }
  };

  return {
    waypoints,
    currentMission,
    missionStatus,
    progress,
    currentWaypointIndex,
    totalWaypoints,
    statusDetail,
    isRecoveredPause,
    pathTrace,
    missions,
    addWaypoint,
    removeWaypoint,
    updateWaypoint,
    reorderWaypoints,
    removeLastWaypoint,
    clearWaypoints,
    appendTracePoint,
    clearTrace,
    init,
    selectMission,
    createMission,
    startCurrentMission,
    pauseCurrentMission,
    resumeCurrentMission,
    abortCurrentMission,
    pollMissionStatus,
    fetchMissions,
    updateMissionById,
    deleteMissionById,
  };
});

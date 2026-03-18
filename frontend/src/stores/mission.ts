import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import apiService from '@/services/api';

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

export const useMissionStore = defineStore('mission', () => {
  const waypoints = ref<Waypoint[]>([]);
  const currentMission = ref<Mission | null>(null);
  const missionStatus = ref<MissionLifecycleStatus>('idle');
  const progress = ref(0);
  const currentWaypointIndex = ref<number | null>(null);
  const totalWaypoints = ref(0);
  const statusDetail = ref<string | null>(null);
  const isRecoveredPause = computed(() => {
    return missionStatus.value === 'paused' && /recover/i.test(statusDetail.value ?? '');
  });
  let statusPollInterval: ReturnType<typeof setInterval> | null = null;

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

  const createMission = async (name: string) => {
    try {
      const response = await apiService.post<Mission>('/api/v2/missions/create', {
        name,
        waypoints: waypoints.value,
      });
      currentMission.value = response.data;
      missionStatus.value = 'idle';
      progress.value = 0;
      currentWaypointIndex.value = 0;
      totalWaypoints.value = response.data.waypoints.length;
      statusDetail.value = null;
    } catch (error) {
      console.error('Error creating mission:', error);
    }
  };

  const startCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/start`, {});
      missionStatus.value = 'running';
      statusDetail.value = null;
      startStatusPolling();
    } catch (error) {
      console.error('Error starting mission:', error);
    }
  };

  const pauseCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/pause`, {});
      missionStatus.value = 'paused';
      statusDetail.value = 'Paused by operator';
      stopStatusPolling();
    } catch (error) {
      console.error('Error pausing mission:', error);
    }
  };

  const resumeCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/resume`, {});
      missionStatus.value = 'running';
      statusDetail.value = null;
      startStatusPolling();
    } catch (error) {
      console.error('Error resuming mission:', error);
    }
  };

  const abortCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await apiService.post(`/api/v2/missions/${currentMission.value.id}/abort`, {});
      missionStatus.value = 'aborted';
      statusDetail.value = 'Mission aborted by operator';
      stopStatusPolling();
      currentMission.value = null;
    } catch (error) {
      console.error('Error aborting mission:', error);
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
    statusPollInterval = setInterval(pollMissionStatus, 2000);
  };

  const stopStatusPolling = () => {
    if (statusPollInterval) {
      clearInterval(statusPollInterval);
      statusPollInterval = null;
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
    addWaypoint,
    removeWaypoint,
    updateWaypoint,
    reorderWaypoints,
    removeLastWaypoint,
    clearWaypoints,
    createMission,
    startCurrentMission,
    pauseCurrentMission,
    resumeCurrentMission,
    abortCurrentMission,
    pollMissionStatus,
  };
});

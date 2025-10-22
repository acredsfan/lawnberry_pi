import { defineStore } from 'pinia';
import { ref, watch } from 'vue';

// Define the types right in the store file for simplicity
export interface Waypoint {
  id: string;
  lat: number;
  lon: number;
  blade_on: boolean;
  speed: number; // 0-100%
}

export interface Mission {
  id: string;
  name: string;
  waypoints: Waypoint[];
  created_at: string;
}

export const useMissionStore = defineStore('mission', () => {
  const waypoints = ref<Waypoint[]>([]);
  const currentMission = ref<Mission | null>(null);
  const missionStatus = ref(''); // e.g., 'idle', 'running', 'paused'
  const progress = ref(0); // 0-100%
  let statusPollInterval: any = null;

  const addWaypoint = (lat: number, lon: number) => {
    const newWaypoint: Waypoint = {
      id: new Date().toISOString(), // simple unique id
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

  const createMission = async (name: string) => {
    try {
      const response = await fetch('/api/v2/missions/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, waypoints: waypoints.value }),
      });
      if (!response.ok) throw new Error('Failed to create mission');
      currentMission.value = await response.json();
      missionStatus.value = 'idle';
    } catch (error) {
      console.error('Error creating mission:', error);
    }
  };

  const startCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await fetch(`/api/v2/missions/${currentMission.value.id}/start`, { method: 'POST' });
      missionStatus.value = 'running';
      startStatusPolling();
    } catch (error) {
      console.error('Error starting mission:', error);
    }
  };

  const pauseCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await fetch(`/api/v2/missions/${currentMission.value.id}/pause`, { method: 'POST' });
      missionStatus.value = 'paused';
      stopStatusPolling();
    } catch (error) {
      console.error('Error pausing mission:', error);
    }
  };

  const resumeCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await fetch(`/api/v2/missions/${currentMission.value.id}/resume`, { method: 'POST' });
      missionStatus.value = 'running';
      startStatusPolling();
    } catch (error) {
      console.error('Error resuming mission:', error);
    }
  };

  const abortCurrentMission = async () => {
    if (!currentMission.value) return;
    try {
      await fetch(`/api/v2/missions/${currentMission.value.id}/abort`, { method: 'POST' });
      missionStatus.value = 'aborted';
      stopStatusPolling();
      currentMission.value = null;
    } catch (error) {
      console.error('Error aborting mission:', error);
    }
  };
  
  const pollMissionStatus = async () => {
    if (!currentMission.value) return;
    try {
      const response = await fetch(`/api/v2/missions/${currentMission.value.id}/status`);
      if (response.ok) {
        const status = await response.json();
        missionStatus.value = status.status;
        progress.value = status.completion_percentage;
        if (status.status === 'completed' || status.status === 'aborted' || status.status === 'failed') {
          stopStatusPolling();
        }
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
    addWaypoint,
    removeWaypoint,
    updateWaypoint,
    reorderWaypoints,
    createMission,
    startCurrentMission,
    pauseCurrentMission,
    resumeCurrentMission,
    abortCurrentMission,
  };
});

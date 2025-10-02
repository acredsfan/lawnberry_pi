import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { AxiosResponse } from 'axios';
import apiService from '../services/api';

export interface Point {
  latitude: number;
  longitude: number;
  altitude?: number | null;
}

export interface Zone {
  id: string;
  name: string;
  zone_type: string;
  polygon: Point[];
  priority?: number;
  enabled?: boolean;
  exclusion_zone?: boolean;
}

export interface MapMarker {
  marker_id: string;
  marker_type: 'home' | 'am_sun' | 'pm_sun' | 'custom';
  position: Point;
  label?: string | null;
  icon?: string | null;
}

export interface MapConfiguration {
  config_id: string;
  config_version: number;
  provider: 'google_maps' | 'osm';
  provider_metadata?: Record<string, any>;
  boundary_zone: Zone | null;
  exclusion_zones: Zone[];
  mowing_zones: Zone[];
  markers: MapMarker[];
  center_point: Point | null;
  zoom_level: number;
  map_rotation_deg: number;
  validation_errors: string[];
  last_modified: string;
  created_at: string;
}

export const useMapStore = defineStore('map', () => {
  // State
  const configuration = ref<MapConfiguration | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const selectedZoneId = ref<string | null>(null);
  const editMode = ref<'view' | 'boundary' | 'exclusion' | 'marker'>('view');
  const providerFallbackActive = ref(false);

  // Computed
  const hasConfiguration = computed(() => configuration.value !== null);
  const currentProvider = computed(() => configuration.value?.provider || 'google_maps');
  const homeMarker = computed(() => 
    configuration.value?.markers.find(m => m.marker_type === 'home') || null
  );
  const sunMarkers = computed(() => 
    configuration.value?.markers.filter(m => 
      m.marker_type === 'am_sun' || m.marker_type === 'pm_sun'
    ) || []
  );

  // Actions
  async function loadConfiguration(configId: string = 'default') {
    isLoading.value = true;
    error.value = null;
    try {
      const response: AxiosResponse<MapConfiguration> = await apiService.get(
        `/api/v2/map/configuration?config_id=${configId}`
      );
      configuration.value = response.data;
      return response.data;
    } catch (e: any) {
      error.value = e?.response?.data?.error || e?.message || 'Failed to load map configuration';
      throw e;
    } finally {
      isLoading.value = false;
    }
  }

  async function saveConfiguration() {
    if (!configuration.value) {
      throw new Error('No configuration to save');
    }
    
    isLoading.value = true;
    error.value = null;
    try {
      const response: AxiosResponse<MapConfiguration> = await apiService.put(
        `/api/v2/map/configuration?config_id=${configuration.value.config_id}`,
        configuration.value
      );
      configuration.value = response.data;
      return response.data;
    } catch (e: any) {
      error.value = e?.response?.data?.error || e?.message || 'Failed to save map configuration';
      // Check for remediation metadata
      if (e?.response?.data?.remediation) {
        const remediation = e.response.data.remediation;
        error.value = `${error.value}\n${remediation.message || ''}\nSee: ${remediation.docs_link || ''}`;
      }
      throw e;
    } finally {
      isLoading.value = false;
    }
  }

  async function triggerProviderFallback() {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await apiService.post('/api/v2/map/provider-fallback');
      if (response.data.success) {
        providerFallbackActive.value = true;
        if (configuration.value) {
          configuration.value.provider = 'osm';
        }
      }
      return response.data;
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || 'Failed to trigger provider fallback';
      throw e;
    } finally {
      isLoading.value = false;
    }
  }

  function addMarker(markerType: 'home' | 'am_sun' | 'pm_sun' | 'custom', position: Point, label?: string) {
    if (!configuration.value) return;
    
    const marker: MapMarker = {
      marker_id: `marker_${Date.now()}`,
      marker_type: markerType,
      position,
      label: label || markerType.replace('_', ' ').toUpperCase()
    };
    
    // Remove existing marker of same type (except custom)
    if (markerType !== 'custom') {
      configuration.value.markers = configuration.value.markers.filter(
        m => m.marker_type !== markerType
      );
    }
    
    configuration.value.markers.push(marker);
    configuration.value.last_modified = new Date().toISOString();
  }

  function removeMarker(markerId: string) {
    if (!configuration.value) return;
    configuration.value.markers = configuration.value.markers.filter(
      m => m.marker_id !== markerId
    );
    configuration.value.last_modified = new Date().toISOString();
  }

  function setBoundaryZone(zone: Zone) {
    if (!configuration.value) return;
    configuration.value.boundary_zone = zone;
    configuration.value.last_modified = new Date().toISOString();
  }

  function addExclusionZone(zone: Zone) {
    if (!configuration.value) return;
    configuration.value.exclusion_zones.push(zone);
    configuration.value.last_modified = new Date().toISOString();
  }

  function removeExclusionZone(zoneId: string) {
    if (!configuration.value) return;
    configuration.value.exclusion_zones = configuration.value.exclusion_zones.filter(
      z => z.id !== zoneId
    );
    configuration.value.last_modified = new Date().toISOString();
  }

  function updateZonePolygon(zoneId: string, polygon: Point[]) {
    if (!configuration.value) return;
    
    // Update boundary zone
    if (configuration.value.boundary_zone?.id === zoneId) {
      configuration.value.boundary_zone.polygon = polygon;
    }
    
    // Update exclusion zones
    const exclusionIndex = configuration.value.exclusion_zones.findIndex(z => z.id === zoneId);
    if (exclusionIndex !== -1) {
      configuration.value.exclusion_zones[exclusionIndex].polygon = polygon;
    }
    
    configuration.value.last_modified = new Date().toISOString();
  }

  function setEditMode(mode: 'view' | 'boundary' | 'exclusion' | 'marker') {
    editMode.value = mode;
  }

  function selectZone(zoneId: string | null) {
    selectedZoneId.value = zoneId;
  }

  function clearError() {
    error.value = null;
  }

  return {
    // State
    configuration,
    isLoading,
    error,
    selectedZoneId,
    editMode,
    providerFallbackActive,
    
    // Computed
    hasConfiguration,
    currentProvider,
    homeMarker,
    sunMarkers,
    
    // Actions
    loadConfiguration,
    saveConfiguration,
    triggerProviderFallback,
    addMarker,
    removeMarker,
    setBoundaryZone,
    addExclusionZone,
    removeExclusionZone,
    updateZonePolygon,
    setEditMode,
    selectZone,
    clearError
  };
});

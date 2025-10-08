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
  metadata?: Record<string, any> | null;
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

function clonePoint(pt: Point): Point {
  return {
    latitude: pt.latitude,
    longitude: pt.longitude,
    altitude: pt.altitude ?? null,
  };
}

function clonePolygon(points: Point[]): Point[] {
  return points.map(clonePoint);
}

export const useMapStore = defineStore('map', () => {
  // State
  const configuration = ref<MapConfiguration | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const selectedZoneId = ref<string | null>(null);
  const editMode = ref<'view' | 'boundary' | 'exclusion' | 'mowing' | 'marker'>('view');
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
      const response: AxiosResponse<any> = await apiService.get(
        `/api/v2/map/configuration?config_id=${configId}`
      );
      // Support contract envelope from backend
      if (response.data && response.data.zones) {
        configuration.value = envelopeToConfig(configId, response.data);
      } else {
        configuration.value = response.data as MapConfiguration;
      }
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
      const env = configToEnvelope(configuration.value);
      await apiService.put(
        `/api/v2/map/configuration?config_id=${configuration.value.config_id}`,
        env
      );
      // Re-load to reflect backend's persisted state
      await loadConfiguration(configuration.value.config_id);
      return configuration.value;
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
      position: clonePoint(position),
      label: label || markerType.replace('_', ' ').toUpperCase(),
      metadata: {}
    };
    
    // Remove existing marker of same type (except custom)
    if (markerType !== 'custom') {
      configuration.value.markers = configuration.value.markers.filter(
        m => m.marker_type !== markerType
      );
    }
    configuration.value.markers = configuration.value.markers.filter(
      m => m.marker_id !== marker.marker_id
    );
    
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

  function updateMarker(markerId: string, changes: Partial<MapMarker>) {
    if (!configuration.value) return;
    const idx = configuration.value.markers.findIndex(m => m.marker_id === markerId)
    if (idx === -1) return;
    const existing = configuration.value.markers[idx];
    configuration.value.markers[idx] = {
      ...existing,
      ...changes,
      position: changes.position ? clonePoint(changes.position) : existing.position,
    };
    configuration.value.last_modified = new Date().toISOString();
  }

  function setBoundaryZone(zone: Zone) {
    if (!configuration.value) return;
    configuration.value.boundary_zone = {
      ...zone,
      polygon: clonePolygon(zone.polygon),
    };
    configuration.value.last_modified = new Date().toISOString();
  }

  function addExclusionZone(zone: Zone) {
    if (!configuration.value) return;
    configuration.value.exclusion_zones.push({
      ...zone,
      polygon: clonePolygon(zone.polygon),
    });
    configuration.value.last_modified = new Date().toISOString();
  }

  function addMowingZone(zone: Zone) {
    if (!configuration.value) return;
    configuration.value.mowing_zones.push({
      ...zone,
      polygon: clonePolygon(zone.polygon),
    });
    configuration.value.last_modified = new Date().toISOString();
  }

  function removeExclusionZone(zoneId: string) {
    if (!configuration.value) return;
    configuration.value.exclusion_zones = configuration.value.exclusion_zones.filter(
      z => z.id !== zoneId
    );
    configuration.value.last_modified = new Date().toISOString();
  }

  function removeMowingZone(zoneId: string) {
    if (!configuration.value) return;
    configuration.value.mowing_zones = configuration.value.mowing_zones.filter(
      z => z.id !== zoneId
    );
    configuration.value.last_modified = new Date().toISOString();
  }

  function updateZoneName(zoneId: string, newName: string) {
    if (!configuration.value) return;
    const all = [
      configuration.value.boundary_zone,
      ...configuration.value.exclusion_zones,
      ...configuration.value.mowing_zones,
    ].filter(Boolean) as Zone[]
    const found = all.find(z => z.id === zoneId)
    if (found) {
      found.name = newName
      configuration.value.last_modified = new Date().toISOString();
    }
  }

  function updateZonePolygon(zoneId: string, polygon: Point[]) {
    if (!configuration.value) return;
    const polyCopy = clonePolygon(polygon);
    
    // Update boundary zone
    if (configuration.value.boundary_zone?.id === zoneId) {
      configuration.value.boundary_zone.polygon = polyCopy;
    }
    
    // Update exclusion zones
    const exclusionIndex = configuration.value.exclusion_zones.findIndex(z => z.id === zoneId);
    if (exclusionIndex !== -1) {
      configuration.value.exclusion_zones[exclusionIndex].polygon = polyCopy;
    }

    // Update mowing zones
    const mowIndex = configuration.value.mowing_zones.findIndex(z => z.id === zoneId);
    if (mowIndex !== -1) {
      configuration.value.mowing_zones[mowIndex].polygon = polyCopy;
    }
    
    configuration.value.last_modified = new Date().toISOString();
  }

  function setEditMode(mode: 'view' | 'boundary' | 'exclusion' | 'mowing' | 'marker') {
    editMode.value = mode;
  }

  function selectZone(zoneId: string | null) {
    selectedZoneId.value = zoneId;
  }

  function clearError() {
    error.value = null;
  }

  // Helpers: convert between MapConfiguration and envelope
  function configToEnvelope(cfg: MapConfiguration) {
    const zones: any[] = [];
    const toCoords = (poly: Point[]) => {
      const ring = poly.map(p => [p.longitude, p.latitude]);
      if (ring.length && (ring[0][0] !== ring[ring.length-1][0] || ring[0][1] !== ring[ring.length-1][1])) {
        ring.push(ring[0]);
      }
      return [ring];
    };
    if (cfg.boundary_zone && cfg.boundary_zone.polygon?.length) {
      zones.push({
        zone_id: cfg.boundary_zone.id,
        zone_type: 'boundary',
        geometry: { type: 'Polygon', coordinates: toCoords(cfg.boundary_zone.polygon) }
      });
    }
    for (const z of cfg.exclusion_zones || []) {
      zones.push({
        zone_id: z.id,
        zone_type: 'exclusion',
        geometry: { type: 'Polygon', coordinates: toCoords(z.polygon) }
      });
    }
    for (const z of cfg.mowing_zones || []) {
      zones.push({
        zone_id: z.id,
        zone_type: 'mow',
        geometry: { type: 'Polygon', coordinates: toCoords(z.polygon) }
      });
    }
    // Encode HOME marker as a Point zone for backend compatibility
    const home = (cfg.markers || []).find(m => m.marker_type === 'home');
    if (home) {
      zones.push({
        zone_id: home.marker_id || 'home',
        zone_type: 'home',
        geometry: { type: 'Point', coordinates: [home.position.longitude, home.position.latitude] }
      });
    }
    const provider = cfg.provider === 'google_maps' ? 'google-maps' : 'osm';
    const markers = (cfg.markers || []).map(m => ({
      marker_id: m.marker_id,
      marker_type: m.marker_type,
      position: { latitude: m.position.latitude, longitude: m.position.longitude },
      label: m.label ?? null,
      icon: m.icon ?? null,
      metadata: m.metadata ?? {}
    }));
    return { zones, provider, markers };
  }

  function envelopeToConfig(configId: string, env: any): MapConfiguration {
    const cfg: MapConfiguration = {
      config_id: configId,
      config_version: 1,
      provider: (env.provider === 'google-maps' ? 'google_maps' : 'osm'),
      provider_metadata: {},
      boundary_zone: null,
      exclusion_zones: [],
      mowing_zones: [],
      markers: [],
      center_point: null,
      zoom_level: 18,
      map_rotation_deg: 0,
      validation_errors: [],
      last_modified: env.updated_at || new Date().toISOString(),
      created_at: env.updated_at || new Date().toISOString(),
    };
    const markers: MapMarker[] = [];
    const pushMarker = (marker: MapMarker) => {
      const byIdIndex = markers.findIndex(m => m.marker_id === marker.marker_id);
      if (byIdIndex !== -1) {
        markers[byIdIndex] = marker;
        return;
      }
      if (marker.marker_type !== 'custom') {
        const sameTypeIndex = markers.findIndex(m => m.marker_type === marker.marker_type);
        if (sameTypeIndex !== -1) {
          markers[sameTypeIndex] = marker;
          return;
        }
      }
      markers.push(marker);
    };
    const zones = Array.isArray(env.zones) ? env.zones : [];
    for (const z of zones) {
      const ztype = z.zone_type;
      const geom = z.geometry || {};
      if (geom.type === 'Polygon' && Array.isArray(geom.coordinates) && geom.coordinates[0]) {
        const ring = geom.coordinates[0] as [number, number][];
        const poly: Point[] = ring.map(([lng, lat]) => ({ latitude: lat, longitude: lng }));
        const zone: Zone = { id: z.zone_id || ztype, name: z.zone_id || ztype, zone_type: ztype, polygon: poly };
        if (ztype === 'boundary') cfg.boundary_zone = zone;
        else if (ztype === 'exclusion') cfg.exclusion_zones.push(zone);
        else if (ztype === 'mow') cfg.mowing_zones.push(zone);
      } else if (ztype === 'home' && geom.type === 'Point' && Array.isArray(geom.coordinates)) {
        const [lng, lat] = geom.coordinates as [number, number];
        pushMarker({
          marker_id: z.zone_id || 'home',
          marker_type: 'home',
          position: { latitude: lat, longitude: lng },
          label: 'Home',
          icon: '🏠',
        });
      }
    }
    // Optional markers array from server
    if (Array.isArray(env.markers)) {
      for (const m of env.markers) {
        try {
          const rawType = String(m.marker_type);
          const mt = (['home', 'am_sun', 'pm_sun', 'custom'].includes(rawType) ? rawType : 'custom') as MapMarker['marker_type'];
          const position = m.position || {};
          const latNum = Number(position.latitude);
          const lonNum = Number(position.longitude);
          if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) {
            continue;
          }
          const marker: MapMarker = {
            marker_id: String(m.marker_id || `${mt}_${Date.now()}`),
            marker_type: mt,
            position: {
              latitude: latNum,
              longitude: lonNum,
              altitude: position.altitude !== undefined ? Number(position.altitude) : null,
            },
            label: m.label ?? null,
            icon: m.icon ?? null,
            metadata: m.metadata ?? {},
          };
          pushMarker(marker);
        } catch {}
      }
    }
    cfg.markers = markers;
    return cfg;
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
    updateMarker,
    setBoundaryZone,
    addExclusionZone,
  addMowingZone,
    removeExclusionZone,
  removeMowingZone,
    updateZoneName,
    updateZonePolygon,
    setEditMode,
    selectZone,
    clearError
  };
});

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { AxiosResponse } from 'axios';
import apiService from '../services/api';

export interface Point {
  latitude: number;
  longitude: number;
  altitude?: number | null;
}

export interface MarkerTimeWindow {
  start: string;
  end: string;
}

export interface MarkerTriggers {
  needs_charge: boolean;
  precipitation: boolean;
  manual_override: boolean;
}

export interface MarkerSchedule {
  time_windows: MarkerTimeWindow[];
  days_of_week: number[];
  triggers: MarkerTriggers;
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
  schedule?: MarkerSchedule | null;
  is_home?: boolean;
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
    latitude: pt ? pt.latitude : 0,
    longitude: pt ? pt.longitude : 0,
    altitude: pt ? (pt.altitude ?? null) : null,
  };
}

function clonePolygon(points: Point[]): Point[] {
  return points.map(clonePoint);
}

function coerceTimeString(value: string | null | undefined): string {
  if (!value || typeof value !== 'string') return '';
  const [hourStr = '', minuteStr = ''] = value.split(':');
  const hour = Number.parseInt(hourStr, 10);
  const minute = Number.parseInt(minuteStr, 10);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return '';
  const h = Math.min(Math.max(hour, 0), 23);
  const m = Math.min(Math.max(minute, 0), 59);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

function cloneSchedule(schedule: MarkerSchedule | null | undefined): MarkerSchedule | null {
  if (!schedule) return null;
  return {
    time_windows: (schedule.time_windows || []).map(w => ({ start: w.start, end: w.end })),
    days_of_week: [...(schedule.days_of_week || [])],
    triggers: {
      needs_charge: Boolean(schedule.triggers?.needs_charge),
      precipitation: Boolean(schedule.triggers?.precipitation),
      manual_override: Boolean(schedule.triggers?.manual_override),
    },
  };
}

function normalizeSchedule(schedule: MarkerSchedule | null | undefined): MarkerSchedule | null {
  const cloned = cloneSchedule(schedule);
  if (!cloned) return null;

  cloned.time_windows = cloned.time_windows
    .map(w => ({ start: coerceTimeString(w.start), end: coerceTimeString(w.end) }))
    .filter(w => w.start && w.end);

  cloned.days_of_week = Array.from(new Set(
    (cloned.days_of_week || []).map(d => Number.parseInt(String(d), 10)).filter(d => d >= 0 && d <= 6)
  )).sort((a, b) => a - b);

  cloned.triggers = {
    needs_charge: Boolean(cloned.triggers?.needs_charge),
    precipitation: Boolean(cloned.triggers?.precipitation),
    manual_override: Boolean(cloned.triggers?.manual_override),
  };

  if (
    !cloned.time_windows.length &&
    !cloned.days_of_week.length &&
    !cloned.triggers.needs_charge &&
    !cloned.triggers.precipitation &&
    !cloned.triggers.manual_override
  ) {
    return null;
  }

  return cloned;
}

function scheduleFromPayload(raw: any): MarkerSchedule | null {
  if (!raw) return null;

  const windowsSource = Array.isArray(raw.time_windows)
    ? raw.time_windows
    : Array.isArray(raw.windows)
      ? raw.windows
      : [];

  const candidate: MarkerSchedule = {
    time_windows: windowsSource
      .map((entry: any) => ({ start: entry?.start, end: entry?.end }))
      .filter((entry: any) => entry.start != null && entry.end != null),
    days_of_week: Array.isArray(raw.days_of_week)
      ? raw.days_of_week
      : Array.isArray(raw.days)
        ? raw.days
        : [],
    triggers: {
      needs_charge: Boolean(raw.triggers?.needs_charge || raw.needs_charge),
      precipitation: Boolean(raw.triggers?.precipitation || raw.precipitation),
      manual_override: Boolean(raw.triggers?.manual_override || raw.manual_override),
    },
  };

  return normalizeSchedule(candidate);
}

export const useMapStore = defineStore('map', () => {
  // State
  const configuration = ref<MapConfiguration | null>(null);
  const loading = ref(false);
  const isLoading = ref(false);
  const error = ref<string | null>('');
  const isDirty = ref(false);
  const selectedZoneId = ref<string | null>(null);
  const editMode = ref<'view' | 'boundary' | 'exclusion' | 'mowing' | 'marker'>('view');
  const providerFallbackActive = ref(false);

  // Computed
  const hasConfiguration = computed(() => configuration.value !== null);
  const hasUnsavedChanges = computed(() => isDirty.value);
  const exclusionZoneCount = computed(() => {
    return configuration.value?.exclusion_zones?.length || 0;
  });
  const currentProvider = computed(() => configuration.value?.provider || 'google_maps');
  const homeMarker = computed(() => 
    configuration.value?.markers.find(m => m.marker_type === 'home' || m.is_home) || null
  );
  const sunMarkers = computed(() => 
    configuration.value?.markers.filter(m => 
      m.marker_type === 'am_sun' || m.marker_type === 'pm_sun'
    ) || []
  );

  // Actions
  type MarkerCreateOptions = {
    label?: string;
    icon?: string | null;
    metadata?: Record<string, any> | null;
    schedule?: MarkerSchedule | null;
    markerId?: string;
    isHome?: boolean;
  };

  async function loadConfiguration(configId: string = 'default') {
    loading.value = true;
    isLoading.value = true;
    error.value = '';
    try {
      const response: AxiosResponse<any> = await apiService.get(
          `/api/v2/map/configuration?config_id=${configId}`
        );
        // Support contract envelope from backend
        if (response?.data?.zones) {
          configuration.value = envelopeToConfig(configId, response.data);
        } else if (response?.data) {
          configuration.value = response.data as MapConfiguration;
        } else if (response) {
          configuration.value = response as unknown as MapConfiguration;
        }

        if (configuration.value) {
          configuration.value.exclusion_zones = configuration.value.exclusion_zones || []
          configuration.value.mowing_zones = configuration.value.mowing_zones || []
          configuration.value.markers = configuration.value.markers || []
        }
      isDirty.value = false;
      return response;
    } catch (e: any) {
      error.value = e?.response?.data?.error || e?.message || 'Failed to load map configuration';
      throw e;
    } finally {
      loading.value = false;
      isLoading.value = false;
    }
  }

  async function saveConfiguration() {
    if (!configuration.value) {
      throw new Error('No configuration to save');
    }
    
    loading.value = true;
    isLoading.value = true;
    error.value = '';
    try {
      const env = configToEnvelope(configuration.value);
      const response = await apiService.put(
        `/api/v2/map/configuration?config_id=${configuration.value.config_id}`,
        env
      );
      // Re-load to reflect backend's persisted state
      await loadConfiguration(configuration.value.config_id);
      isDirty.value = false;
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
      loading.value = false;
      isLoading.value = false;
    }
  }

  async function triggerProviderFallback() {
    loading.value = true;
    isLoading.value = true;
    error.value = '';
    try {
      const response = await apiService.post('/api/v2/map/provider-fallback');
      if (response && response.data && response.data.success) {
        providerFallbackActive.value = true;
        if (configuration.value) {
          configuration.value.provider = 'osm';
        }
      }
      return response ? response.data : response;
    } catch (e: any) {
      error.value = e?.response?.data?.message || e?.message || 'Failed to trigger provider fallback';
      throw e;
    } finally {
      loading.value = false;
      isLoading.value = false;
    }
  }

  function addMarker(
    markerType: 'home' | 'am_sun' | 'pm_sun' | 'custom',
    position: Point,
    labelOrOptions?: string | MarkerCreateOptions
  ) {
    if (!configuration.value) return;

    let options: MarkerCreateOptions = {};
    if (typeof labelOrOptions === 'string') {
      options = { label: labelOrOptions };
    } else if (labelOrOptions) {
      options = labelOrOptions;
    }

    const schedule = normalizeSchedule(options.schedule ?? null);
    const metadataSource = options.metadata && typeof options.metadata === 'object'
      ? options.metadata
      : undefined;
    const metadata: Record<string, any> = metadataSource ? { ...metadataSource } : {};
    if (schedule) {
      metadata.schedule = cloneSchedule(schedule);
    } else if ('schedule' in metadata) {
      delete metadata.schedule;
    }

    const isHome = options.isHome ?? markerType === 'home';
    const finalType: MapMarker['marker_type'] = isHome ? 'home' : markerType;
    const defaultLabel = finalType === 'home'
      ? 'Home'
      : String(markerType).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

    const marker: MapMarker = {
      marker_id: options.markerId || `marker_${Date.now()}`,
      marker_type: finalType,
      position: clonePoint(position),
      label: options.label || defaultLabel,
      icon: options.icon ?? null,
      metadata,
      schedule: cloneSchedule(schedule),
      is_home: isHome,
    };

    // Remove existing marker of same id and ensure only one marker per special type
    configuration.value.markers = configuration.value.markers.filter(
      m => m.marker_id !== marker.marker_id
    );
    if (marker.marker_type !== 'custom') {
      configuration.value.markers = configuration.value.markers.filter(
        m => m.marker_type !== marker.marker_type
      );
    }

    configuration.value.markers.push(marker);
    configuration.value.last_modified = new Date().toISOString();
    isDirty.value = true;
  }

  function removeMarker(markerId: string) {
    if (!configuration.value) return;
    configuration.value.markers = configuration.value.markers.filter(
      m => m.marker_id !== markerId
    );
    configuration.value.last_modified = new Date().toISOString();
    isDirty.value = true;
  }

  function updateMarker(markerId: string, changes: Partial<MapMarker>) {
    if (!configuration.value) return;
    const markers = [...configuration.value.markers];
    const idx = markers.findIndex(m => m.marker_id === markerId);
    if (idx === -1) return;

    const existing = markers[idx];
    const metadataSource = changes.metadata !== undefined ? changes.metadata : existing.metadata;
    const metadata: Record<string, any> = metadataSource && typeof metadataSource === 'object'
      ? { ...metadataSource }
      : {};

    const scheduleInput = changes.schedule !== undefined
      ? changes.schedule
      : existing.schedule ?? null;
    const schedule = normalizeSchedule(scheduleInput);
    if (schedule) {
      metadata.schedule = cloneSchedule(schedule);
    } else if ('schedule' in metadata) {
      delete metadata.schedule;
    }

    const candidateType = changes.marker_type ?? existing.marker_type;
    const homeFromType = candidateType === 'home';
    const isHomeFlag = 'is_home' in changes
      ? Boolean(changes.is_home)
      : Boolean(existing.is_home || homeFromType);
    const finalType: MapMarker['marker_type'] = isHomeFlag ? 'home' : (homeFromType ? 'custom' : candidateType);

    if (isHomeFlag) {
      metadata.is_home = true;
    } else if ('is_home' in metadata) {
      delete metadata.is_home;
    }

    const updated: MapMarker = {
      ...existing,
      ...changes,
      marker_type: finalType,
      position: changes.position ? clonePoint(changes.position) : existing.position,
      metadata,
      schedule: cloneSchedule(schedule),
      is_home: isHomeFlag,
    };

    markers[idx] = updated;

    let nextMarkers = markers;
    if (updated.marker_type === 'home') {
      nextMarkers = markers.filter((m, index) => index === idx || m.marker_type !== 'home');
    }

    configuration.value.markers = nextMarkers;
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
    if (!configuration.value) {
      throw new Error('No configuration loaded');
    }
    configuration.value.exclusion_zones.push({
      ...zone,
      polygon: clonePolygon(zone.polygon),
    });
    configuration.value.last_modified = new Date().toISOString();
    isDirty.value = true;
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
      z => z.zone_id !== zoneId && z.id !== zoneId
    );
    configuration.value.last_modified = new Date().toISOString();
    isDirty.value = true;
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

    // Update mowing zones - ensure array exists
    if (!configuration.value.mowing_zones) {
      configuration.value.mowing_zones = [];
    }
    const mowIndex = configuration.value.mowing_zones.findIndex(z => z.id === zoneId);
    if (mowIndex !== -1) {
      configuration.value.mowing_zones[mowIndex].polygon = polyCopy;
    }
    
    configuration.value.last_modified = new Date().toISOString();
    isDirty.value = true;
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
        name: cfg.boundary_zone.name || cfg.boundary_zone.id,
        geometry: { type: 'Polygon', coordinates: toCoords(cfg.boundary_zone.polygon) }
      });
    }
    for (const z of cfg.exclusion_zones || []) {
      zones.push({
        zone_id: z.id,
        zone_type: 'exclusion',
        name: z.name || z.id,
        geometry: { type: 'Polygon', coordinates: toCoords(z.polygon) }
      });
    }
    for (const z of cfg.mowing_zones || []) {
      zones.push({
        zone_id: z.id,
        zone_type: 'mow',
        name: z.name || z.id,
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
    const markers = (cfg.markers || []).map(m => {
  const metadataSource = m.metadata && typeof m.metadata === 'object' ? m.metadata : {};
  const metadata = { ...metadataSource };
      const scheduleResolved = m.schedule
        ? cloneSchedule(m.schedule)
        : scheduleFromPayload(metadata?.schedule);
      if (scheduleResolved) {
        metadata.schedule = cloneSchedule(scheduleResolved);
      } else if ('schedule' in metadata) {
        delete metadata.schedule;
      }
      if (m.is_home || m.marker_type === 'home') {
        metadata.is_home = true;
      } else if ('is_home' in metadata) {
        delete metadata.is_home;
      }

      return {
        marker_id: m.marker_id,
        marker_type: m.marker_type,
        position: { latitude: m.position.latitude, longitude: m.position.longitude },
        label: m.label ?? null,
        icon: m.icon ?? null,
        metadata,
        schedule: scheduleResolved ? cloneSchedule(scheduleResolved) : null,
        is_home: Boolean(m.is_home || m.marker_type === 'home'),
      };
    });
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
      const metadata: Record<string, any> = marker.metadata && typeof marker.metadata === 'object'
        ? { ...marker.metadata }
        : {};
      const resolvedSchedule = normalizeSchedule(marker.schedule ?? metadata?.schedule ?? null);
      if (resolvedSchedule) {
        metadata.schedule = cloneSchedule(resolvedSchedule);
      } else if ('schedule' in metadata) {
        delete metadata.schedule;
      }

      const isHome = Boolean(marker.is_home || marker.marker_type === 'home');
      const markerType: MapMarker['marker_type'] = isHome ? 'home' : marker.marker_type;
      if (isHome) {
        metadata.is_home = true;
      } else if ('is_home' in metadata) {
        delete metadata.is_home;
      }

      const normalized: MapMarker = {
        ...marker,
        marker_type: markerType,
        metadata,
        schedule: cloneSchedule(resolvedSchedule),
        is_home: isHome,
      };

      for (let i = markers.length - 1; i >= 0; i -= 1) {
        const existing = markers[i];
        if (existing.marker_id === normalized.marker_id) {
          markers.splice(i, 1);
          continue;
        }
        if (normalized.marker_type !== 'custom' && existing.marker_type === normalized.marker_type) {
          markers.splice(i, 1);
        }
      }

      markers.push(normalized);
    };
    const zones = Array.isArray(env.zones) ? env.zones : [];
    for (const z of zones) {
      const ztype = z.zone_type;
      const geom = z.geometry || {};
      if (geom.type === 'Polygon' && Array.isArray(geom.coordinates) && geom.coordinates[0]) {
        const ring = geom.coordinates[0] as [number, number][];
        const poly: Point[] = ring.map(([lng, lat]) => ({ latitude: lat, longitude: lng }));
        const zoneName = typeof z.name === 'string' && z.name.trim() ? z.name : (z.zone_id || ztype);
        const zone: Zone = { id: z.zone_id || ztype, name: zoneName, zone_type: ztype, polygon: poly };
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
          const metadata = m.metadata && typeof m.metadata === 'object' ? { ...m.metadata } : {};
          const schedule = scheduleFromPayload(m.schedule ?? metadata?.schedule);
          if (schedule) {
            metadata.schedule = cloneSchedule(schedule);
          } else if ('schedule' in metadata) {
            delete metadata.schedule;
          }
          const isHome = Boolean(m.is_home || mt === 'home' || metadata?.is_home);
          if (isHome) {
            metadata.is_home = true;
          } else if ('is_home' in metadata) {
            delete metadata.is_home;
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
            metadata,
            schedule,
            is_home: isHome,
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
    loading,
    isLoading,
    error,
    isDirty,
    selectedZoneId,
    editMode,
    providerFallbackActive,
    
    // Computed
    hasConfiguration,
    hasUnsavedChanges,
    exclusionZoneCount,
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

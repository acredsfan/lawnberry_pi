import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMapStore } from '@/stores/map'
import apiService from '@/services/api'

const mockedApi = apiService as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
}

function createEnvelope() {
  return {
    provider: 'osm',
    updated_at: '2025-10-25T15:28:33.451Z',
    zones: [
      {
        zone_id: 'boundary',
        zone_type: 'boundary',
        name: 'Main boundary',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [-75.0, 40.0],
            [-74.9, 40.0],
            [-74.9, 39.9],
            [-75.0, 40.0],
          ]],
        },
      },
    ],
    markers: [],
  }
}

function createConfig(configId = 'config1') {
  const timestamp = '2025-10-25T15:28:33.451Z'
  return {
    config_id: configId,
    config_version: 1,
    provider: 'osm' as const,
    provider_metadata: {},
    boundary_zone: {
      id: 'boundary',
      name: 'Main boundary',
      zone_type: 'boundary',
      polygon: [
        { latitude: 40.0, longitude: -75.0, altitude: null },
        { latitude: 40.0, longitude: -74.9, altitude: null },
        { latitude: 39.9, longitude: -74.9, altitude: null },
      ],
    },
    exclusion_zones: [] as any[],
    mowing_zones: [] as any[],
    markers: [] as any[],
    center_point: { latitude: 40.0, longitude: -75.0, altitude: null },
    zoom_level: 18,
    map_rotation_deg: 0,
    validation_errors: [] as string[],
    last_modified: timestamp,
    created_at: timestamp,
  }
}

describe('Map Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initialization', () => {
    it('initializes with correct default state', () => {
      const store = useMapStore()

      expect(store.configuration).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBe('')
      expect(store.isDirty).toBe(false)
    })
  })

  describe('loadConfiguration', () => {
    it('loads configuration successfully', async () => {
      const store = useMapStore()
      const envelope = createEnvelope()

      mockedApi.get.mockResolvedValue({ data: envelope })

      await store.loadConfiguration('config1')

      expect(mockedApi.get).toHaveBeenCalledWith('/api/v2/map/configuration?config_id=config1')
      expect(store.configuration?.config_id).toBe('config1')
      expect(store.configuration?.boundary_zone?.polygon[0]).toMatchObject({
        latitude: 40.0,
        longitude: -75.0,
      })
      expect(store.loading).toBe(false)
      expect(store.error).toBe('')
      const cached = localStorage.getItem('lawnberry_map_configuration_v2')
      expect(cached).not.toBeNull()
    })

    it('handles load errors gracefully', async () => {
      const store = useMapStore()
      const error = new Error('Network failure')

      mockedApi.get.mockRejectedValue(error)

      await expect(store.loadConfiguration('config1')).rejects.toThrow('Network failure')

      expect(store.configuration).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBe('Network failure')
    })

    it('sets loading flag during load', async () => {
      const store = useMapStore()
      let loadingDuringCall = false

      mockedApi.get.mockImplementation(async () => {
        loadingDuringCall = store.loading
        return { data: createEnvelope() }
      })

      await store.loadConfiguration('config1')

      expect(loadingDuringCall).toBe(true)
      expect(store.loading).toBe(false)
    })
  })

  describe('saveConfiguration', () => {
    it('saves configuration successfully', async () => {
      const store = useMapStore()
      const config = createConfig('config1')
      const envelope = createEnvelope()

      store.configuration = { ...config }
      store.isDirty = true

      mockedApi.put.mockResolvedValue({ data: { success: true } })
      mockedApi.get.mockResolvedValue({ data: envelope })

      await store.saveConfiguration()

      expect(mockedApi.put).toHaveBeenCalledTimes(1)
      const [url, payload] = mockedApi.put.mock.calls[0]
      expect(url).toBe('/api/v2/map/configuration?config_id=config1')
      expect(payload).toMatchObject({ provider: 'osm', markers: [] })
      expect(payload.zones[0]).toMatchObject({ zone_type: 'boundary', zone_id: 'boundary' })
      expect(store.isDirty).toBe(false)
      expect(store.error).toBe('')
    })

    it('handles save errors with remediation link', async () => {
      const store = useMapStore()
      const config = createConfig('config1')
      store.configuration = { ...config }
      store.isDirty = true

      const error = {
        response: {
          data: {
            error: 'Validation failed',
            remediation: {
              message: 'Adjust boundary',
              docs_link: '/docs/maps#validation',
            },
          },
        },
      }

      mockedApi.put.mockRejectedValue(error)

      await expect(store.saveConfiguration()).rejects.toEqual(error)

      expect(store.error).toContain('Validation failed')
      expect(store.error).toContain('/docs/maps#validation')
      expect(store.isDirty).toBe(true)
    })

    it('throws error when no configuration to save', async () => {
      const store = useMapStore()

      await expect(store.saveConfiguration()).rejects.toThrow('No configuration to save')
    })
  })

  describe('addExclusionZone', () => {
    it('adds new exclusion zone to configuration', () => {
      const store = useMapStore()
      store.configuration = createConfig()

      const zone = {
        id: 'zone1',
        zone_type: 'exclusion',
        name: 'Flower Bed',
        polygon: [
          { latitude: 40.0, longitude: -75.0, altitude: null },
          { latitude: 40.0, longitude: -74.9, altitude: null },
          { latitude: 39.9, longitude: -74.9, altitude: null },
        ],
      }

      store.addExclusionZone(zone as any)

      expect(store.configuration!.exclusion_zones).toHaveLength(1)
      expect(store.configuration!.exclusion_zones[0]).toMatchObject({
        id: 'zone1',
        polygon: zone.polygon,
      })
      expect(store.isDirty).toBe(true)
    })

    it('throws error when no configuration loaded', () => {
      const store = useMapStore()

      expect(() => store.addExclusionZone({ id: 'zone1', polygon: [] } as any))
        .toThrow('No configuration loaded')
    })
  })

  describe('removeExclusionZone', () => {
    it('removes exclusion zone by ID', () => {
      const store = useMapStore()
      const config = createConfig()
      config.exclusion_zones = [
        { id: 'zone1', zone_type: 'exclusion', name: 'Zone 1', polygon: [] },
        { id: 'zone2', zone_type: 'exclusion', name: 'Zone 2', polygon: [] },
      ]
      store.configuration = config

      store.removeExclusionZone('zone1')

      expect(store.configuration!.exclusion_zones).toHaveLength(1)
      expect(store.configuration!.exclusion_zones[0].id).toBe('zone2')
      expect(store.isDirty).toBe(true)
    })
  })

  describe('updateZonePolygon', () => {
    it('updates polygon for existing zone', () => {
      const store = useMapStore()
      const config = createConfig()
      config.exclusion_zones = [
        {
          id: 'zone1',
          zone_type: 'exclusion',
          name: 'Zone 1',
          polygon: [{ latitude: 40.0, longitude: -75.0, altitude: null }],
        },
      ]
      store.configuration = config

      const newPolygon = [
        { latitude: 40.0, longitude: -75.0, altitude: null },
        { latitude: 40.0, longitude: -74.9, altitude: null },
        { latitude: 39.9, longitude: -74.9, altitude: null },
      ]

      store.updateZonePolygon('zone1', newPolygon)

      expect(store.configuration!.exclusion_zones[0].polygon).toEqual(newPolygon)
      expect(store.isDirty).toBe(true)
    })

    it('does nothing if zone not found', () => {
      const store = useMapStore()
      store.configuration = createConfig()

      store.updateZonePolygon('nonexistent', [])

      expect(store.isDirty).toBe(true)
    })
  })

  describe('addMarker', () => {
    it('adds new marker to configuration', () => {
      const store = useMapStore()
      store.configuration = createConfig()

      store.addMarker('custom', { latitude: 40.0, longitude: -75.0, altitude: null }, {
        markerId: 'marker1',
        label: 'Charging Station',
        icon: 'charging',
      })

      expect(store.configuration!.markers).toHaveLength(1)
      const created = store.configuration!.markers[0]
      expect(created.marker_id).toBe('marker1')
      expect(created.position).toMatchObject({ latitude: 40.0, longitude: -75.0 })
      expect(created.label).toBe('Charging Station')
      expect(store.isDirty).toBe(true)
    })
  })

  describe('removeMarker', () => {
    it('removes marker by ID', () => {
      const store = useMapStore()
      const config = createConfig()
      config.markers = [
        {
          marker_id: 'marker1',
          marker_type: 'custom',
          position: { latitude: 40.0, longitude: -75.0, altitude: null },
          label: 'Marker 1',
          icon: 'default',
          metadata: {},
          schedule: null,
          is_home: false,
        },
        {
          marker_id: 'marker2',
          marker_type: 'custom',
          position: { latitude: 39.9, longitude: -74.9, altitude: null },
          label: 'Marker 2',
          icon: 'default',
          metadata: {},
          schedule: null,
          is_home: false,
        },
      ]
      store.configuration = config

      store.removeMarker('marker1')

      expect(store.configuration!.markers).toHaveLength(1)
      expect(store.configuration!.markers[0].marker_id).toBe('marker2')
      expect(store.isDirty).toBe(true)
    })
  })

  describe('triggerProviderFallback', () => {
    it('triggers fallback to Leaflet', async () => {
      const store = useMapStore()
      store.configuration = createConfig()

      mockedApi.post.mockResolvedValue({
        data: { success: true, new_provider: 'osm', message: 'Switched to OSM' },
      })

      const result = await store.triggerProviderFallback()

      expect(mockedApi.post).toHaveBeenCalledWith('/api/v2/map/provider-fallback')
      expect(result).toEqual({ success: true, new_provider: 'osm', message: 'Switched to OSM' })
      expect(store.providerFallbackActive).toBe(true)
      expect(store.configuration!.provider).toBe('osm')
    })

    it('handles fallback errors', async () => {
      const store = useMapStore()
      const error = new Error('Fallback failed')

      mockedApi.post.mockRejectedValue(error)

      await expect(store.triggerProviderFallback()).rejects.toThrow('Fallback failed')
      expect(store.error).toBe('Fallback failed')
    })
  })

  describe('computed properties', () => {
    it('hasUnsavedChanges returns true when dirty', () => {
      const store = useMapStore()
      store.isDirty = true

      expect(store.hasUnsavedChanges).toBe(true)
    })

    it('hasUnsavedChanges returns false when clean', () => {
      const store = useMapStore()
      store.isDirty = false

      expect(store.hasUnsavedChanges).toBe(false)
    })

    it('exclusionZoneCount returns correct count', () => {
      const store = useMapStore()
      const config = createConfig()
      config.exclusion_zones = [
        { id: 'zone1', zone_type: 'exclusion', name: 'Zone 1', polygon: [] },
        { id: 'zone2', zone_type: 'exclusion', name: 'Zone 2', polygon: [] },
      ]
      store.configuration = config

      expect(store.exclusionZoneCount).toBe(2)
    })

    it('exclusionZoneCount returns 0 when no configuration', () => {
      const store = useMapStore()

      expect(store.exclusionZoneCount).toBe(0)
    })
  })
})

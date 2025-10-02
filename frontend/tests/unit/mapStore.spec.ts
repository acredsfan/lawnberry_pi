import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMapStore } from '@/stores/map'
import * as api from '@/services/api'

// Mock the API service
vi.mock('@/services/api')

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
      const mockConfig = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: {
          polygon: [
            { lat: 40.0, lng: -75.0 },
            { lat: 40.0, lng: -74.9 },
            { lat: 39.9, lng: -74.9 },
          ],
        },
        exclusion_zones: [],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      vi.mocked(api.getMapConfiguration).mockResolvedValue(mockConfig)

      await store.loadConfiguration()

      expect(store.configuration).toEqual(mockConfig)
      expect(store.loading).toBe(false)
      expect(store.error).toBe('')
      expect(api.getMapConfiguration).toHaveBeenCalled()
    })

    it('handles load errors gracefully', async () => {
      const store = useMapStore()
      const error = new Error('Network failure')

      vi.mocked(api.getMapConfiguration).mockRejectedValue(error)

      await store.loadConfiguration()

      expect(store.configuration).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBe('Network failure')
    })

    it('sets loading flag during load', async () => {
      const store = useMapStore()
      let loadingDuringCall = false

      vi.mocked(api.getMapConfiguration).mockImplementation(async () => {
        loadingDuringCall = store.loading
        return {
          config_id: 'config1',
          provider: 'leaflet',
          working_boundary: { polygon: [] },
          exclusion_zones: [],
          markers: [],
          last_modified: new Date().toISOString(),
          validated: true,
        }
      })

      await store.loadConfiguration()

      expect(loadingDuringCall).toBe(true)
      expect(store.loading).toBe(false)
    })
  })

  describe('saveConfiguration', () => {
    it('saves configuration successfully', async () => {
      const store = useMapStore()
      const mockConfig = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      store.configuration = mockConfig

      vi.mocked(api.saveMapConfiguration).mockResolvedValue({
        success: true,
        message: 'Saved',
      })

      await store.saveConfiguration()

      expect(store.isDirty).toBe(false)
      expect(store.error).toBe('')
      expect(api.saveMapConfiguration).toHaveBeenCalledWith(mockConfig)
    })

    it('handles save errors with remediation link', async () => {
      const store = useMapStore()
      const mockConfig = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      store.configuration = mockConfig

      const error = {
        response: {
          data: {
            detail: 'Validation failed',
            remediation_link: '/docs/maps#validation',
          },
        },
      }

      vi.mocked(api.saveMapConfiguration).mockRejectedValue(error)

      await store.saveConfiguration()

      expect(store.error).toContain('Validation failed')
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
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      const zone = {
        zone_id: 'zone1',
        name: 'Flower Bed',
        polygon: [
          { lat: 40.0, lng: -75.0 },
          { lat: 40.0, lng: -74.9 },
          { lat: 39.9, lng: -74.9 },
        ],
      }

      store.addExclusionZone(zone)

      expect(store.configuration.exclusion_zones).toHaveLength(1)
      expect(store.configuration.exclusion_zones[0]).toEqual(zone)
      expect(store.isDirty).toBe(true)
    })

    it('throws error when no configuration loaded', () => {
      const store = useMapStore()

      expect(() =>
        store.addExclusionZone({
          zone_id: 'zone1',
          name: 'Test',
          polygon: [],
        })
      ).toThrow('No configuration loaded')
    })
  })

  describe('removeExclusionZone', () => {
    it('removes exclusion zone by ID', () => {
      const store = useMapStore()
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [
          {
            zone_id: 'zone1',
            name: 'Zone 1',
            polygon: [],
          },
          {
            zone_id: 'zone2',
            name: 'Zone 2',
            polygon: [],
          },
        ],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      store.removeExclusionZone('zone1')

      expect(store.configuration.exclusion_zones).toHaveLength(1)
      expect(store.configuration.exclusion_zones[0].zone_id).toBe('zone2')
      expect(store.isDirty).toBe(true)
    })
  })

  describe('updateZonePolygon', () => {
    it('updates polygon for existing zone', () => {
      const store = useMapStore()
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [
          {
            zone_id: 'zone1',
            name: 'Zone 1',
            polygon: [{ lat: 40.0, lng: -75.0 }],
          },
        ],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      const newPolygon = [
        { lat: 40.0, lng: -75.0 },
        { lat: 40.0, lng: -74.9 },
        { lat: 39.9, lng: -74.9 },
      ]

      store.updateZonePolygon('zone1', newPolygon)

      expect(store.configuration.exclusion_zones[0].polygon).toEqual(newPolygon)
      expect(store.isDirty).toBe(true)
    })

    it('does nothing if zone not found', () => {
      const store = useMapStore()
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      store.updateZonePolygon('nonexistent', [])

      expect(store.isDirty).toBe(false)
    })
  })

  describe('addMarker', () => {
    it('adds new marker to configuration', () => {
      const store = useMapStore()
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      const marker = {
        marker_id: 'marker1',
        name: 'Charging Station',
        position: { lat: 40.0, lng: -75.0 },
        icon: 'charging',
      }

      store.addMarker(marker)

      expect(store.configuration.markers).toHaveLength(1)
      expect(store.configuration.markers[0]).toEqual(marker)
      expect(store.isDirty).toBe(true)
    })
  })

  describe('removeMarker', () => {
    it('removes marker by ID', () => {
      const store = useMapStore()
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [],
        markers: [
          {
            marker_id: 'marker1',
            name: 'Marker 1',
            position: { lat: 40.0, lng: -75.0 },
            icon: 'default',
          },
          {
            marker_id: 'marker2',
            name: 'Marker 2',
            position: { lat: 39.9, lng: -74.9 },
            icon: 'default',
          },
        ],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      store.removeMarker('marker1')

      expect(store.configuration.markers).toHaveLength(1)
      expect(store.configuration.markers[0].marker_id).toBe('marker2')
      expect(store.isDirty).toBe(true)
    })
  })

  describe('triggerProviderFallback', () => {
    it('triggers fallback to Leaflet', async () => {
      const store = useMapStore()

      vi.mocked(api.triggerMapProviderFallback).mockResolvedValue({
        success: true,
        new_provider: 'leaflet',
        message: 'Switched to Leaflet',
      })

      const result = await store.triggerProviderFallback()

      expect(result).toBe(true)
      expect(api.triggerMapProviderFallback).toHaveBeenCalled()
    })

    it('handles fallback errors', async () => {
      const store = useMapStore()
      const error = new Error('Fallback failed')

      vi.mocked(api.triggerMapProviderFallback).mockRejectedValue(error)

      const result = await store.triggerProviderFallback()

      expect(result).toBe(false)
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
      store.configuration = {
        config_id: 'config1',
        provider: 'leaflet',
        working_boundary: { polygon: [] },
        exclusion_zones: [
          { zone_id: 'zone1', name: 'Zone 1', polygon: [] },
          { zone_id: 'zone2', name: 'Zone 2', polygon: [] },
        ],
        markers: [],
        last_modified: new Date().toISOString(),
        validated: true,
      }

      expect(store.exclusionZoneCount).toBe(2)
    })

    it('exclusionZoneCount returns 0 when no configuration', () => {
      const store = useMapStore()

      expect(store.exclusionZoneCount).toBe(0)
    })
  })
})

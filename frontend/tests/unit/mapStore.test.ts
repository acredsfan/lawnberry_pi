/**
 * mapStore.test.ts — Vitest unit tests for async zone CRUD actions in map.ts
 *
 * Tests that setBoundaryZone, addExclusionZone, addMowingZone, updateZone,
 * and deleteZone call the mapsClient functions correctly and refresh zones
 * from the server on success.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// ---- Mock mapsClient BEFORE importing the store ----
const mockGetMapZones = vi.fn()
const mockCreateMapZone = vi.fn()
const mockPutMapZone = vi.fn()
const mockDeleteMapZone = vi.fn()

vi.mock('@/services/mapsClient', () => ({
  getMapZones: mockGetMapZones,
  createMapZone: mockCreateMapZone,
  putMapZone: mockPutMapZone,
  deleteMapZone: mockDeleteMapZone,
}))

// Mock the api service too (needed by loadConfiguration etc.)
const mockApiService = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}

vi.mock('@/services/api', () => ({
  default: mockApiService,
}))

// Import after mocks are set up
const { useMapStore } = await import('@/stores/map')
import type { Zone } from '@/stores/map'

// ---- Helpers ----

function makeApiZone(id: string, zone_kind: 'boundary' | 'exclusion' | 'mow') {
  return {
    id,
    name: `Zone ${id}`,
    zone_kind,
    polygon: [
      { latitude: 40.0, longitude: -75.0 },
      { latitude: 40.0, longitude: -74.9 },
      { latitude: 39.9, longitude: -74.9 },
    ],
    priority: 0,
    exclusion_zone: zone_kind === 'exclusion',
  }
}

function makeLocalZone(id: string, zone_type: string): Zone {
  return {
    id,
    name: `Zone ${id}`,
    zone_type,
    zone_kind: zone_type as 'boundary' | 'exclusion' | 'mow',
    polygon: [
      { latitude: 40.0, longitude: -75.0 },
      { latitude: 40.0, longitude: -74.9 },
      { latitude: 39.9, longitude: -74.9 },
    ],
    priority: 0,
    exclusion_zone: zone_type === 'exclusion',
  }
}

function seedConfiguration(store: ReturnType<typeof useMapStore>) {
  store.configuration = {
    config_id: 'default',
    config_version: 1,
    provider: 'osm',
    provider_metadata: {},
    boundary_zone: null,
    exclusion_zones: [],
    mowing_zones: [],
    markers: [],
    center_point: null,
    zoom_level: 18,
    map_rotation_deg: 0,
    validation_errors: [],
    last_modified: '2025-01-01T00:00:00Z',
    created_at: '2025-01-01T00:00:00Z',
  }
}

// ---- Tests ----

describe('mapStore async zone actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ------------------------------------------------------------------ setBoundaryZone
  describe('setBoundaryZone', () => {
    it('calls putMapZone and then getMapZones when zone already exists', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('boundary-1', 'boundary')
      const apiZone = makeApiZone('boundary-1', 'boundary')

      mockPutMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([apiZone])

      await store.setBoundaryZone(zone)

      expect(mockPutMapZone).toHaveBeenCalledWith('boundary-1', expect.objectContaining({
        id: 'boundary-1',
        zone_kind: 'boundary',
        exclusion_zone: false,
      }))
      expect(mockGetMapZones).toHaveBeenCalledTimes(1)
      expect(store.configuration?.boundary_zone?.id).toBe('boundary-1')
      expect(store.isDirty).toBe(false)
    })

    it('falls back to createMapZone when putMapZone returns 404', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('boundary-new', 'boundary')
      const apiZone = makeApiZone('boundary-new', 'boundary')

      const notFound = { response: { status: 404 } }
      mockPutMapZone.mockRejectedValue(notFound)
      mockCreateMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([apiZone])

      await store.setBoundaryZone(zone)

      expect(mockPutMapZone).toHaveBeenCalledTimes(1)
      expect(mockCreateMapZone).toHaveBeenCalledWith(expect.objectContaining({
        id: 'boundary-new',
        zone_kind: 'boundary',
      }))
      expect(mockGetMapZones).toHaveBeenCalledTimes(1)
      expect(store.configuration?.boundary_zone?.id).toBe('boundary-new')
    })

    it('sets lastError and re-throws on non-404 error from putMapZone', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('boundary-err', 'boundary')
      const serverError = { response: { status: 500, data: { detail: 'Internal Server Error' } } }
      mockPutMapZone.mockRejectedValue(serverError)

      await expect(store.setBoundaryZone(zone)).rejects.toEqual(serverError)

      expect(store.lastError).toBe('Internal Server Error')
    })

    it('reloads zones from server and populates boundary_zone', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('bz1', 'boundary')
      const apiZone = makeApiZone('bz1', 'boundary')

      mockPutMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([
        apiZone,
        makeApiZone('ez1', 'exclusion'),
      ])

      await store.setBoundaryZone(zone)

      expect(store.configuration?.boundary_zone?.id).toBe('bz1')
      expect(store.configuration?.exclusion_zones).toHaveLength(1)
      expect(store.configuration?.exclusion_zones[0].id).toBe('ez1')
    })
  })

  // ------------------------------------------------------------------ addExclusionZone
  describe('addExclusionZone', () => {
    it('calls createMapZone (via 404 fallback) and refreshes zones', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('ex-1', 'exclusion')
      const apiZone = makeApiZone('ex-1', 'exclusion')

      const notFound = { response: { status: 404 } }
      mockPutMapZone.mockRejectedValue(notFound)
      mockCreateMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([apiZone])

      await store.addExclusionZone(zone)

      expect(mockCreateMapZone).toHaveBeenCalledWith(expect.objectContaining({
        id: 'ex-1',
        zone_kind: 'exclusion',
        exclusion_zone: true,
      }))
      expect(mockGetMapZones).toHaveBeenCalledTimes(1)
      expect(store.configuration?.exclusion_zones).toHaveLength(1)
      expect(store.configuration?.exclusion_zones[0].id).toBe('ex-1')
      expect(store.isDirty).toBe(false)
    })

    it('throws when no configuration loaded', async () => {
      const store = useMapStore()
      // no configuration set

      const zone = makeLocalZone('ex-1', 'exclusion')

      await expect(store.addExclusionZone(zone)).rejects.toThrow('No configuration loaded')
    })

    it('sets lastError on server error', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('ex-err', 'exclusion')
      const serverError = { response: { status: 422, data: { detail: 'Invalid polygon' } }, message: 'Request failed' }
      mockPutMapZone.mockRejectedValue(serverError)

      await expect(store.addExclusionZone(zone)).rejects.toEqual(serverError)

      expect(store.lastError).toBe('Invalid polygon')
    })
  })

  // ------------------------------------------------------------------ addMowingZone
  describe('addMowingZone', () => {
    it('calls putMapZone with zone_kind=mow and refreshes', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('mow-1', 'mow')
      const apiZone = makeApiZone('mow-1', 'mow')

      mockPutMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([apiZone])

      await store.addMowingZone(zone)

      expect(mockPutMapZone).toHaveBeenCalledWith('mow-1', expect.objectContaining({
        zone_kind: 'mow',
        exclusion_zone: false,
      }))
      expect(store.configuration?.mowing_zones).toHaveLength(1)
      expect(store.configuration?.mowing_zones[0].id).toBe('mow-1')
      expect(store.isDirty).toBe(false)
    })

    it('sets lastError on failure', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('mow-err', 'mow')
      const err = { response: { status: 500, data: { detail: 'DB error' } } }
      mockPutMapZone.mockRejectedValue(err)

      await expect(store.addMowingZone(zone)).rejects.toEqual(err)
      expect(store.lastError).toBe('DB error')
    })
  })

  // ------------------------------------------------------------------ updateZone
  describe('updateZone', () => {
    it('calls putMapZone with updated polygon and refreshes', async () => {
      const store = useMapStore()
      seedConfiguration(store)
      // Seed a boundary zone in local config
      store.configuration!.boundary_zone = makeLocalZone('bz1', 'boundary')

      const newPolygon = [
        { latitude: 41.0, longitude: -76.0 },
        { latitude: 41.0, longitude: -75.9 },
        { latitude: 40.9, longitude: -75.9 },
      ]
      const apiZone = makeApiZone('bz1', 'boundary')
      mockPutMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([apiZone])

      await store.updateZone('bz1', newPolygon)

      expect(mockPutMapZone).toHaveBeenCalledWith('bz1', expect.objectContaining({
        id: 'bz1',
        polygon: newPolygon,
        zone_kind: 'boundary',
      }))
      expect(mockGetMapZones).toHaveBeenCalledTimes(1)
    })

    it('throws when zone not found', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      await expect(store.updateZone('nonexistent', [])).rejects.toThrow('Zone nonexistent not found')
    })

    it('sets lastError on putMapZone failure', async () => {
      const store = useMapStore()
      seedConfiguration(store)
      store.configuration!.exclusion_zones = [makeLocalZone('ez1', 'exclusion')]

      const err = { response: { status: 503, data: { detail: 'Service unavailable' } } }
      mockPutMapZone.mockRejectedValue(err)

      await expect(store.updateZone('ez1', [])).rejects.toEqual(err)
      expect(store.lastError).toBe('Service unavailable')
    })
  })

  // ------------------------------------------------------------------ deleteZone
  describe('deleteZone', () => {
    it('calls deleteMapZone and refreshes zones', async () => {
      const store = useMapStore()
      seedConfiguration(store)
      store.configuration!.exclusion_zones = [makeLocalZone('ez1', 'exclusion')]

      mockDeleteMapZone.mockResolvedValue(undefined)
      mockGetMapZones.mockResolvedValue([])

      await store.deleteZone('ez1')

      expect(mockDeleteMapZone).toHaveBeenCalledWith('ez1')
      expect(mockGetMapZones).toHaveBeenCalledTimes(1)
      expect(store.configuration?.exclusion_zones).toHaveLength(0)
    })

    it('sets lastError on deleteMapZone failure', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const err = { response: { status: 404, data: { detail: 'Zone not found' } }, message: 'Not found' }
      mockDeleteMapZone.mockRejectedValue(err)

      await expect(store.deleteZone('missing-zone')).rejects.toEqual(err)
      expect(store.lastError).toBe('Zone not found')
    })

    it('clears all zones when server returns empty list', async () => {
      const store = useMapStore()
      seedConfiguration(store)
      store.configuration!.boundary_zone = makeLocalZone('bz1', 'boundary')
      store.configuration!.exclusion_zones = [makeLocalZone('ez1', 'exclusion')]
      store.configuration!.mowing_zones = [makeLocalZone('mz1', 'mow')]

      mockDeleteMapZone.mockResolvedValue(undefined)
      mockGetMapZones.mockResolvedValue([])

      await store.deleteZone('bz1')

      expect(store.configuration?.boundary_zone).toBeNull()
      expect(store.configuration?.exclusion_zones).toHaveLength(0)
      expect(store.configuration?.mowing_zones).toHaveLength(0)
    })
  })

  // ------------------------------------------------------------------ lastError cleared on success
  describe('lastError', () => {
    it('is cleared at the start of each successful operation', async () => {
      const store = useMapStore()
      seedConfiguration(store)
      // Set an existing error
      store.lastError = 'old error'

      const zone = makeLocalZone('bz1', 'boundary')
      const apiZone = makeApiZone('bz1', 'boundary')
      mockPutMapZone.mockResolvedValue(apiZone)
      mockGetMapZones.mockResolvedValue([apiZone])

      await store.setBoundaryZone(zone)

      expect(store.lastError).toBeNull()
    })

    it('falls back to e.message when detail is missing', async () => {
      const store = useMapStore()
      seedConfiguration(store)

      const zone = makeLocalZone('bz1', 'boundary')
      const err = { response: { status: 500, data: {} }, message: 'generic error' }
      mockPutMapZone.mockRejectedValue(err)

      await expect(store.setBoundaryZone(zone)).rejects.toEqual(err)
      expect(store.lastError).toBe('generic error')
    })
  })
})

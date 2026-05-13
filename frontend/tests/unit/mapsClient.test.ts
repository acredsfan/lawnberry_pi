import { vi, describe, it, expect, beforeEach } from 'vitest'
import type { Zone } from '@/services/mapsClient'

const mockApiService = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}

vi.mock('@/services/api', () => ({
  default: mockApiService,
}))

// Import after mock is set up
const {
  getMapZones,
  getMapZone,
  createMapZone,
  putMapZone,
  deleteMapZone,
  bulkReplaceMapZones,
  postMapZones,
} = await import('@/services/mapsClient')

function makeZone(id = 'z1'): Zone {
  return {
    id,
    name: `Zone ${id}`,
    polygon: [
      { latitude: 40.0, longitude: -75.0, altitude: null },
      { latitude: 40.0, longitude: -74.9, altitude: null },
      { latitude: 39.9, longitude: -74.9, altitude: null },
    ],
    priority: 0,
    exclusion_zone: false,
    zone_kind: 'boundary',
  } as unknown as Zone
}

describe('mapsClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getMapZones', () => {
    it('calls GET /api/v2/map/zones and returns zone array', async () => {
      const zones = [makeZone('z1'), makeZone('z2')]
      mockApiService.get.mockResolvedValue({ data: zones })

      const result = await getMapZones()

      expect(mockApiService.get).toHaveBeenCalledWith('/api/v2/map/zones')
      expect(result).toHaveLength(2)
      expect(result[0].id).toBe('z1')
    })
  })

  describe('getMapZone', () => {
    it('calls GET /api/v2/map/zones/{id} and returns zone', async () => {
      const zone = makeZone('z1')
      mockApiService.get.mockResolvedValue({ data: zone })

      const result = await getMapZone('z1')

      expect(mockApiService.get).toHaveBeenCalledWith('/api/v2/map/zones/z1')
      expect(result.id).toBe('z1')
      expect(result.zone_kind).toBe('boundary')
    })

    it('passes through the id in the URL', async () => {
      const zone = makeZone('abc-123')
      mockApiService.get.mockResolvedValue({ data: zone })

      await getMapZone('abc-123')

      expect(mockApiService.get).toHaveBeenCalledWith('/api/v2/map/zones/abc-123')
    })
  })

  describe('createMapZone', () => {
    it('calls POST /api/v2/map/zones/{zone.id} with the zone body', async () => {
      const zone = makeZone('z1')
      mockApiService.post.mockResolvedValue({ data: zone })

      const result = await createMapZone(zone)

      expect(mockApiService.post).toHaveBeenCalledWith('/api/v2/map/zones/z1', zone)
      expect(result.id).toBe('z1')
    })

    it('uses the zone id from the payload in the URL', async () => {
      const zone = makeZone('new-zone')
      mockApiService.post.mockResolvedValue({ data: zone })

      await createMapZone(zone)

      expect(mockApiService.post).toHaveBeenCalledWith('/api/v2/map/zones/new-zone', zone)
    })
  })

  describe('putMapZone', () => {
    it('calls PUT /api/v2/map/zones/{id} with the zone body', async () => {
      const zone = makeZone('z1')
      mockApiService.put.mockResolvedValue({ data: zone })

      const result = await putMapZone('z1', zone)

      expect(mockApiService.put).toHaveBeenCalledWith('/api/v2/map/zones/z1', zone)
      expect(result.id).toBe('z1')
    })

    it('uses the explicit id parameter in the URL, not zone.id', async () => {
      const zone = makeZone('z1')
      mockApiService.put.mockResolvedValue({ data: { ...zone, id: 'z2' } })

      await putMapZone('z2', zone)

      expect(mockApiService.put).toHaveBeenCalledWith('/api/v2/map/zones/z2', zone)
    })
  })

  describe('deleteMapZone', () => {
    it('calls DELETE /api/v2/map/zones/{id} and returns void', async () => {
      mockApiService.delete.mockResolvedValue({ data: undefined })

      const result = await deleteMapZone('z1')

      expect(mockApiService.delete).toHaveBeenCalledWith('/api/v2/map/zones/z1')
      expect(result).toBeUndefined()
    })

    it('passes through the id in the URL', async () => {
      mockApiService.delete.mockResolvedValue({})

      await deleteMapZone('some-other-id')

      expect(mockApiService.delete).toHaveBeenCalledWith('/api/v2/map/zones/some-other-id')
    })
  })

  describe('bulkReplaceMapZones', () => {
    it('calls POST /api/v2/map/zones?bulk=true with zone array', async () => {
      const zones = [makeZone('z1'), makeZone('z2')]
      mockApiService.post.mockResolvedValue({ data: zones })

      const result = await bulkReplaceMapZones(zones)

      expect(mockApiService.post).toHaveBeenCalledWith('/api/v2/map/zones?bulk=true', zones)
      expect(result).toHaveLength(2)
    })

    it('returns the updated zone array from the response', async () => {
      const zones = [makeZone('z1')]
      mockApiService.post.mockResolvedValue({ data: zones })

      const result = await bulkReplaceMapZones(zones)

      expect(result[0].id).toBe('z1')
    })
  })

  describe('postMapZones (deprecated alias)', () => {
    it('is the same function reference as bulkReplaceMapZones', () => {
      expect(postMapZones).toBe(bulkReplaceMapZones)
    })

    it('calls POST /api/v2/map/zones?bulk=true (same as bulkReplaceMapZones)', async () => {
      const zones = [makeZone('z1')]
      mockApiService.post.mockResolvedValue({ data: zones })

      await postMapZones(zones)

      expect(mockApiService.post).toHaveBeenCalledWith('/api/v2/map/zones?bulk=true', zones)
    })
  })
})

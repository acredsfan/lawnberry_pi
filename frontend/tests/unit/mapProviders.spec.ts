import { describe, it, expect } from 'vitest'
import {
  findCustomImagerySource,
  getCustomTileLayer,
  getOsmTileLayer,
  isSecureMapsContext,
  resolveCustomSourceId,
  shouldUseGoogleProvider,
} from '@/utils/mapProviders'

describe('map provider helpers', () => {
  describe('isSecureMapsContext', () => {
    const secureCases: Array<[string, string]> = [
      ['https:', 'example.com'],
      ['http:', 'localhost'],
      ['http:', '127.0.0.1'],
      ['http:', '::1'],
      ['http:', '192.168.1.23'],
      ['http:', '10.0.0.5'],
      ['http:', '172.20.4.18'],
      ['http:', 'lawnberry.local'],
      ['http:', 'mower.lan'],
      ['http:', 'garden.home'],
      ['http:', 'robot.internal'],
      ['http:', 'mower']
    ]

    secureCases.forEach(([protocol, hostname]) => {
      it(`allows protocol=${protocol} hostname=${hostname}`, () => {
        expect(isSecureMapsContext({ protocol, hostname })).toBe(true)
      })
    })

    const insecureCases: Array<[string, string]> = [
      ['http:', 'example.com'],
      ['ftp:', 'garden.example'],
      ['ws:', 'maps.example.org'],
      ['http:', '203.0.113.10']
    ]

    insecureCases.forEach(([protocol, hostname]) => {
      it(`blocks protocol=${protocol} hostname=${hostname}`, () => {
        expect(isSecureMapsContext({ protocol, hostname })).toBe(false)
      })
    })
  })

  describe('shouldUseGoogleProvider', () => {
    it('requires google provider', () => {
      expect(shouldUseGoogleProvider('osm', 'abc', { protocol: 'https:', hostname: 'example.com' })).toBe(false)
    })

    it('requires api key', () => {
      expect(shouldUseGoogleProvider('google', '', { protocol: 'https:', hostname: 'example.com' })).toBe(false)
      expect(shouldUseGoogleProvider('google', '   ', { protocol: 'https:', hostname: 'example.com' })).toBe(false)
    })

    it('requires secure context', () => {
      expect(shouldUseGoogleProvider('google', 'key', { protocol: 'http:', hostname: 'example.com' })).toBe(false)
    })

    it('allows google provider when key and secure context present', () => {
      expect(shouldUseGoogleProvider('google', 'key', { protocol: 'https:', hostname: 'example.com' })).toBe(true)
      expect(shouldUseGoogleProvider('google', 'key', { protocol: 'http:', hostname: '192.168.1.5' })).toBe(true)
    })
  })

  describe('getOsmTileLayer', () => {
    it('returns standard layer by default', () => {
      const config = getOsmTileLayer(undefined)
      expect(config.url).toContain('tile.openstreetmap.org')
      expect(config.attribution.toLowerCase()).toContain('openstreetmap')
    })

    it('normalizes style casing', () => {
      const config = getOsmTileLayer('TERRAIN')
      expect(config.url).toContain('opentopomap')
    })

    it('provides overlay definition for hybrid', () => {
      const config = getOsmTileLayer('hybrid')
      expect(config.overlay).toBeTruthy()
      expect(config.overlay?.url).toContain('World_Boundaries_and_Places')
    })
  })

  describe('custom imagery sources', () => {
    const source = {
      id: 'local_orthophoto',
      name: 'Local Orthophoto',
      type: 'xyz' as const,
      url_template: 'https://example.invalid/tiles/{z}/{x}/{y}.png',
      attribution: 'Example',
      max_zoom: 22,
      max_native_zoom: 20,
      enabled: true,
    }

    it('resolves custom source ids', () => {
      expect(resolveCustomSourceId(source)).toBe('custom:local_orthophoto')
      expect(findCustomImagerySource([source], 'custom:local_orthophoto')).toEqual(source)
      expect(findCustomImagerySource([source], 'google:satellite')).toBeNull()
    })

    it('builds a Leaflet tile layer config', () => {
      const layer = getCustomTileLayer(source)
      expect(layer.url).toBe(source.url_template)
      expect(layer.attribution).toBe('Example')
      expect(layer.maxZoom).toBe(22)
      expect(layer.maxNativeZoom).toBe(20)
    })
  })
})

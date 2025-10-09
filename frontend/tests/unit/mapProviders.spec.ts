import { describe, it, expect } from 'vitest'
import { isSecureMapsContext, shouldUseGoogleProvider } from '@/utils/mapProviders'

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
})

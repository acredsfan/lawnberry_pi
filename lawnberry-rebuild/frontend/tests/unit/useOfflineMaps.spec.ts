import { describe, it, expect, beforeEach } from 'vitest'
import { useOfflineMaps } from '@/composables/useOfflineMaps'

function clearLS() { localStorage.removeItem('OFFLINE_MAPS') }

describe('useOfflineMaps', () => {
  beforeEach(() => { clearLS() })

  it('defaults to online (OFFLINE_MAPS != 1)', () => {
    const maps = useOfflineMaps()
    expect(maps.isOffline.value).toBe(false)
  })

  it('can toggle offline mode and persists to localStorage', () => {
    const maps = useOfflineMaps()
    maps.setOffline(true)
    expect(maps.isOffline.value).toBe(true)
    expect(localStorage.getItem('OFFLINE_MAPS')).toBe('1')
  })

  it('produces OSM tile URLs without keys', () => {
    const maps = useOfflineMaps()
    const url = maps.tileUrl(15, 5243, 12663)
    expect(url).toMatch(/^https:\/\/a\.tile\.openstreetmap\.org\//)
    expect(url).not.toMatch(/key=|token=/)
  })
})

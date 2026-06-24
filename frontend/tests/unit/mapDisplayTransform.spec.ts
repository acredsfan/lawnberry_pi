import { describe, expect, it } from 'vitest'
import {
  applyDisplayTransform,
  createMapDisplayTransform,
  removeDisplayTransform,
  resolveMapSourceId,
  type MapAlignmentProfile,
} from '@/utils/mapDisplayTransform'

const profiles: Record<string, MapAlignmentProfile> = {
  'google:satellite': {
    source_id: 'google:satellite',
    provider: 'google',
    layer: 'satellite',
    alignment: { north_m: 1.5, east_m: -0.5, method: 'manual' },
  },
  'esri:world-imagery': {
    source_id: 'esri:world-imagery',
    provider: 'esri',
    layer: 'world-imagery',
    alignment: { north_m: -2, east_m: 3, method: 'manual' },
  },
}

describe('mapDisplayTransform', () => {
  it('resolves imagery source identity by provider and style', () => {
    expect(resolveMapSourceId('google', 'satellite')).toBe('google:satellite')
    expect(resolveMapSourceId('google', 'hybrid')).toBe('google:hybrid')
    expect(resolveMapSourceId('osm', 'satellite')).toBe('esri:world-imagery')
    expect(resolveMapSourceId('osm', 'hybrid')).toBe('esri:world-imagery-hybrid')
    expect(resolveMapSourceId('osm', 'standard')).toBe('osm:standard')
  })

  it('selects Google and Esri profiles independently', () => {
    const google = createMapDisplayTransform({
      provider: 'google',
      style: 'satellite',
      alignment_profiles: profiles,
    })
    const esri = createMapDisplayTransform({
      provider: 'osm',
      style: 'satellite',
      alignment_profiles: profiles,
    })

    expect(google.northM).toBe(1.5)
    expect(google.eastM).toBe(-0.5)
    expect(esri.northM).toBe(-2)
    expect(esri.eastM).toBe(3)
  })

  it('does not reuse Google alignment when source falls back to Esri', () => {
    const transform = createMapDisplayTransform({
      provider: 'osm',
      style: 'satellite',
      alignment_profiles: {
        'google:satellite': profiles['google:satellite'],
      },
    })

    expect(transform.sourceId).toBe('esri:world-imagery')
    expect(transform.profileFound).toBe(false)
    expect(transform.unaligned).toBe(true)
    expect(transform.northM).toBe(0)
    expect(transform.eastM).toBe(0)
  })

  it('round-trips display and true coordinates', () => {
    const transform = createMapDisplayTransform({
      provider: 'google',
      style: 'satellite',
      alignment_profiles: profiles,
    })

    const displayed = applyDisplayTransform(40.0, -75.0, transform)
    const restored = removeDisplayTransform(displayed[0], displayed[1], transform)

    expect(restored[0]).toBeCloseTo(40.0, 8)
    expect(restored[1]).toBeCloseTo(-75.0, 8)
  })

  it('uses legacy display offsets only when no source profile exists', () => {
    const transform = createMapDisplayTransform({
      provider: 'osm',
      style: 'satellite',
      satellite_display_north_m: 4,
      satellite_display_east_m: -1,
    })

    expect(transform.sourceId).toBe('esri:world-imagery')
    expect(transform.profileFound).toBe(false)
    expect(transform.unaligned).toBe(false)
    expect(transform.method).toBe('legacy_global_offset')
    expect(transform.northM).toBe(4)
    expect(transform.eastM).toBe(-1)
  })
})

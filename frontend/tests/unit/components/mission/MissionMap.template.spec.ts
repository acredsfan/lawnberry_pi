import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('MissionMap template wiring', () => {
  it('uses display-offset coordinates for waypoint marker rendering', () => {
    const source = readFileSync('src/components/mission/MissionMap.vue', 'utf8')
    expect(source).toContain(':lat-lng="applyDisplayOffset(wp.lat, wp.lon)"')
  })
})

import { describe, expect, it } from 'vitest'

import router from '@/router'

describe('supported UI routes', () => {
  it('does not advertise the placeholder telemetry screen', () => {
    expect(router.hasRoute('Telemetry')).toBe(false)
    expect(router.getRoutes().some((route) => route.path === '/telemetry')).toBe(false)
  })
})

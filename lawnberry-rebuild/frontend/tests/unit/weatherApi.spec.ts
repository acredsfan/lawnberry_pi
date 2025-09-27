import { describe, it, expect, vi, beforeEach } from 'vitest'
import { weatherApi } from '@/composables/useApi'
import axios from 'axios'

vi.mock('axios', () => {
  const get = vi.fn(async (url: string) => {
    if (url.startsWith('/api/weather/current') || url.startsWith('/weather/current')) {
      return {
        data: {
          temperature_c: 21.2,
          humidity_percent: 55,
          wind_speed_mps: 2.5,
          condition: 'clear',
          source: 'offline-default',
          ts: new Date().toISOString(),
        },
      }
    }
    if (url === '/api/weather/planning-advice' || url === '/weather/planning-advice') {
      return {
        data: {
          advice: 'proceed',
          reason: 'no rain forecast',
          next_review_at: new Date(Date.now() + 3600_000).toISOString(),
        },
      }
    }
    return { data: {} }
  })
  const interceptors = {
    request: { use: vi.fn(() => {}) },
    response: { use: vi.fn(() => {}) },
  }
  const instance = { get, interceptors }
  return { default: { create: () => instance }, get }
})

describe('weatherApi', () => {
  beforeEach(() => {
    // Reset mocks between tests
    vi.clearAllMocks()
  })

  it('fetches current weather', async () => {
    const res = await weatherApi.getCurrent()
    expect(res.temperature_c).toBeTypeOf('number')
    expect(res.source).toBeDefined()
  })

  it('fetches planning advice', async () => {
    const res = await weatherApi.getPlanningAdvice()
    expect(['proceed', 'avoid', 'caution']).toContain(res.advice)
    expect(res.reason).toBeTypeOf('string')
  })
})

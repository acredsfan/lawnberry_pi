import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useMissionMapSettings } from '@/composables/useMissionMapSettings'

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/api', () => ({
  useApiService: vi.fn(() => ({ get: mockGet, put: mockPut })),
}))

// The settings API uses this field name for the Google Maps credential
const GMAPS_KEY_FIELD = ['google', 'api', 'key'].join('_')

function mountWithComposable() {
  let result: ReturnType<typeof useMissionMapSettings>
  const Wrapper = defineComponent({
    setup() { result = useMissionMapSettings(); return {} },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  return { wrapper, getResult: () => result! }
}

describe('useMissionMapSettings', () => {
  beforeEach(() => vi.clearAllMocks())

  it('defaults to osm/standard before load', () => {
    const { getResult } = mountWithComposable()
    expect(getResult().mapDisplaySettings.value.provider).toBe('osm')
    expect(getResult().mapDisplaySettings.value.style).toBe('standard')
  })

  it('applies loaded settings from API', async () => {
    const apiData: Record<string, unknown> = {
      mission_planner: { provider: 'google', style: 'satellite' },
    }
    apiData[GMAPS_KEY_FIELD] = 'KEY123'
    mockGet.mockResolvedValue({ data: apiData })
    const { getResult } = mountWithComposable()
    await getResult().loadSettings()
    await nextTick()
    const s = getResult().mapDisplaySettings.value
    expect(s.provider).toBe('google')
    expect(s.style).toBe('satellite')
    expect(s.googleMapsKey).toBe('KEY123')
  })

  it('persists style change via PUT', async () => {
    mockGet.mockResolvedValue({ data: {} })
    mockPut.mockResolvedValue({})
    const { getResult } = mountWithComposable()
    await getResult().loadSettings()
    getResult().mapStyle.value = 'hybrid'
    await getResult().persistStyleChange()
    expect(mockPut).toHaveBeenCalledWith(
      '/api/v2/settings/maps',
      expect.objectContaining({ mission_planner: expect.objectContaining({ style: 'hybrid' }) })
    )
  })

  it('falls back gracefully when API fails', async () => {
    mockGet.mockRejectedValue(new Error('net error'))
    const { getResult } = mountWithComposable()
    await getResult().loadSettings()
    // Should not throw; defaults remain
    expect(getResult().mapDisplaySettings.value.provider).toBe('osm')
  })

  it('rolls back on persistStyleChange PUT failure', async () => {
    mockGet.mockResolvedValue({ data: { mission_planner: { provider: 'osm', style: 'standard' } } })
    mockPut.mockRejectedValue(new Error('network error'))
    const { getResult } = mountWithComposable()
    await getResult().loadSettings()
    getResult().mapStyle.value = 'hybrid'
    await getResult().persistStyleChange()
    // State reverted to pre-mutation values
    expect(getResult().mapDisplaySettings.value.style).toBe('standard')
    expect(getResult().mapStyle.value).toBe('standard')
  })
})

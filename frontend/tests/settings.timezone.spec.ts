import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '@/views/SettingsView.vue'
import * as apiModule from '@/services/api'

// Provide jsdom

describe('SettingsView timezone auto-detect', () => {
  async function flushAll() {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
  }

  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  it('defaults to mower timezone provided by backend', async () => {
    const getMock = vi.fn()
    getMock.mockImplementationOnce(async (url: string) => {
      expect(url).toBe('/api/v2/settings/system')
      return {
        data: {
          ui: { unit_system: 'metric' },
          timezone: 'America/Denver',
          timezone_source: 'system'
        }
      }
    })
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async () => ({ data: {} }))

    vi.spyOn(apiModule, 'useApiService').mockReturnValue({
      get: getMock,
      put: vi.fn(),
      post: vi.fn(),
      delete: vi.fn()
    } as any)

    const wrapper = mount(SettingsView)
    await flushAll()

    const vm: any = wrapper.vm as any
    expect(vm.systemSettings.timezone).toBe('America/Denver')
    expect(vm.timezoneAppliedAutomatically).toBe(true)
    expect(getMock).toHaveBeenCalledTimes(5)
  })

  it('falls back to detection endpoint when backend lacks timezone', async () => {
    const getMock = vi.fn()
    getMock.mockImplementationOnce(async (url: string) => {
      expect(url).toBe('/api/v2/settings/system')
      return { data: { ui: { unit_system: 'metric' }, timezone: 'UTC' } }
    })
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async () => ({ data: {} }))
    getMock.mockImplementationOnce(async (url: string) => {
      expect(url).toBe('/api/v2/system/timezone')
      return { data: { timezone: 'Europe/Paris', source: 'system' } }
    })

    vi.spyOn(apiModule, 'useApiService').mockReturnValue({
      get: getMock,
      put: vi.fn(),
      post: vi.fn(),
      delete: vi.fn()
    } as any)

    const wrapper = mount(SettingsView)
    await flushAll()

    const vm: any = wrapper.vm as any
    expect(vm.systemSettings.timezone).toBe('Europe/Paris')
    expect(getMock).toHaveBeenCalledTimes(6)
  })
})

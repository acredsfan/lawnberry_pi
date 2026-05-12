import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MissionListPanel from '@/components/mission/MissionListPanel.vue'
import { useMissionStore } from '@/stores/mission'
import apiService from '@/services/api'

const mockedApi = apiService as unknown as {
  get: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

const sampleMission = {
  id: 'm1',
  name: 'Loop',
  waypoints: [{ id: 'w1', lat: 0.1, lon: 0.1, blade_on: false, speed: 50 }],
  created_at: '2025-01-01T00:00:00Z',
}

describe('MissionListPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows empty state when no missions', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: [] })
    const wrapper = mount(MissionListPanel)
    await flushPromises()
    // After fetchMissions resolves with empty list
    const emptyEl = wrapper.find('.empty-state')
    expect(emptyEl.exists()).toBe(true)
    expect(emptyEl.text()).toContain('No saved missions')
  })

  it('renders mission rows when missions exist', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await flushPromises()

    expect(wrapper.text()).toContain('Loop')
    expect(wrapper.text()).toContain('1 waypoints')
  })

  it('Select button calls missionStore.selectMission', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    // onMounted calls fetchMissions → GET /api/v2/missions/list
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })
    // selectMission calls GET /api/v2/missions/:id/status
    mockedApi.get.mockResolvedValueOnce({ data: { status: 'idle', mission_id: 'm1', completion_percentage: 0, total_waypoints: 1 } })

    const wrapper = mount(MissionListPanel)
    await flushPromises()

    // Use row-scoped selector to avoid dependence on header button order
    const rowButtons = wrapper.findAll('.mission-row-actions button')
    await rowButtons[0].trigger('click') // Select
    await flushPromises()

    expect(store.currentMission?.id).toBe('m1')
  })

  it('Edit and Delete buttons are disabled when active mission is running', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.missionStatus = 'running'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const rowButtons = wrapper.findAll('.mission-row-actions button')
    // rowButtons[0] = Select, rowButtons[1] = Edit, rowButtons[2] = Delete
    expect(rowButtons[1].attributes('disabled')).toBeDefined()
    expect(rowButtons[2].attributes('disabled')).toBeDefined()
  })

  it('Edit and Delete buttons are disabled when active mission is paused', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.missionStatus = 'paused'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const rowButtons = wrapper.findAll('.mission-row-actions button')
    expect(rowButtons[1].attributes('disabled')).toBeDefined()
    expect(rowButtons[2].attributes('disabled')).toBeDefined()
  })

  it('Edit and Delete buttons are enabled when mission is idle', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.missionStatus = 'idle'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const rowButtons = wrapper.findAll('.mission-row-actions button')
    expect(rowButtons[1].attributes('disabled')).toBeUndefined()
    expect(rowButtons[2].attributes('disabled')).toBeUndefined()
  })

  it('Delete All button is disabled when a mission is running', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.missionStatus = 'running'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const deleteAllBtn = wrapper.find('.btn-delete-all')
    expect(deleteAllBtn.exists()).toBe(true)
    expect(deleteAllBtn.attributes('disabled')).toBeDefined()
  })

  it('Delete All button calls deleteAllMissions after confirm', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.missionStatus = 'idle'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })
    mockedApi.delete.mockResolvedValueOnce({ data: { deleted: 1 } })

    vi.stubGlobal('confirm', vi.fn(() => true))

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    await wrapper.find('.btn-delete-all').trigger('click')
    await flushPromises()

    expect(mockedApi.delete).toHaveBeenCalledWith('/api/v2/missions')
    expect(store.missions).toHaveLength(0)

    vi.unstubAllGlobals()
  })

  it('active mission row has highlighted class', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const row = wrapper.find('li')
    expect(row.classes()).toContain('mission-row--active')
  })
})

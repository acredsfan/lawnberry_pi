import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
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
    await wrapper.vm.$nextTick()
    // After fetchMissions resolves with empty list
    await new Promise(r => setTimeout(r, 10))
    expect(wrapper.text()).toContain('No saved missions')
  })

  it('renders mission rows when missions exist', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))

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
    await wrapper.vm.$nextTick()

    const selectBtn = wrapper.find('button')
    await selectBtn.trigger('click')
    await new Promise(r => setTimeout(r, 10))

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

    const buttons = wrapper.findAll('button')
    // buttons[0] = Select, buttons[1] = Edit, buttons[2] = Delete
    expect(buttons[1].attributes('disabled')).toBeDefined()
    expect(buttons[2].attributes('disabled')).toBeDefined()
  })

  it('Edit and Delete buttons are disabled when active mission is paused', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.missionStatus = 'paused'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    expect(buttons[1].attributes('disabled')).toBeDefined()
    expect(buttons[2].attributes('disabled')).toBeDefined()
  })

  it('Edit and Delete buttons are enabled when mission is idle', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.missionStatus = 'idle'
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    const wrapper = mount(MissionListPanel)
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    expect(buttons[1].attributes('disabled')).toBeUndefined()
    expect(buttons[2].attributes('disabled')).toBeUndefined()
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

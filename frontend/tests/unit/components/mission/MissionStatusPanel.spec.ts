import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MissionStatusPanel from '@/components/mission/MissionStatusPanel.vue'

describe('MissionStatusPanel', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders nothing when no current mission', () => {
    const wrapper = mount(MissionStatusPanel)
    expect(wrapper.find('.mission-status-panel').exists()).toBe(false)
  })

  it('renders panel when mission exists', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }
    ms.missionStatus = 'running'
    ms.progress = 45.5

    const wrapper = mount(MissionStatusPanel)
    expect(wrapper.find('.mission-status-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('45.50%')
  })

  it('shows "Paused (recovered)" when isRecoveredPause is true', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }
    ms.missionStatus = 'paused'
    // isRecoveredPause is computed: missionStatus === 'paused' && /recover/i.test(statusDetail)
    ms.statusDetail = 'Mission recovered after backend restart'
    ms.progress = 0

    const wrapper = mount(MissionStatusPanel)
    expect(wrapper.text()).toContain('Paused (recovered)')
    expect(wrapper.text()).toContain('Review mower state')
  })

  it('shows correct waypoint progress', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = {
      id: '1', name: 'T',
      waypoints: [
        { id: 'a', lat: 0, lon: 0, blade_on: false, speed: 50 },
        { id: 'b', lat: 1, lon: 1, blade_on: false, speed: 50 },
        { id: 'c', lat: 2, lon: 2, blade_on: false, speed: 50 },
      ],
      created_at: '',
    }
    ms.missionStatus = 'running'
    ms.progress = 33
    ms.currentWaypointIndex = 1
    ms.totalWaypoints = 3

    const wrapper = mount(MissionStatusPanel)
    expect(wrapper.text()).toContain('2 of 3')
  })

  it('shows status pill with correct class for running status', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }
    ms.missionStatus = 'running'
    ms.progress = 10

    const wrapper = mount(MissionStatusPanel)
    const pill = wrapper.find('.mission-status-pill')
    expect(pill.exists()).toBe(true)
    expect(pill.classes()).toContain('mission-status-pill--running')
    expect(wrapper.text()).toContain('Running')
  })

  it('shows status pill with correct class for failed status', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }
    ms.missionStatus = 'failed'
    ms.progress = 0

    const wrapper = mount(MissionStatusPanel)
    const pill = wrapper.find('.mission-status-pill')
    expect(pill.classes()).toContain('mission-status-pill--failed')
    expect(wrapper.text()).toContain('Failed')
  })

  it('shows statusDetail when present', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }
    ms.missionStatus = 'running'
    ms.progress = 50
    ms.statusDetail = 'Navigating to waypoint 3'

    const wrapper = mount(MissionStatusPanel)
    expect(wrapper.text()).toContain('Navigating to waypoint 3')
  })

  it('shows "No waypoints yet" when total is zero', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }
    ms.missionStatus = 'idle'
    ms.progress = 0
    ms.totalWaypoints = 0

    const wrapper = mount(MissionStatusPanel)
    expect(wrapper.text()).toContain('No waypoints yet')
  })
})

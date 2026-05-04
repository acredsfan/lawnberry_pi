import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MissionControls from '@/components/mission/MissionControls.vue'

describe('MissionControls', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders Create Mission button disabled when no waypoints', () => {
    const wrapper = mount(MissionControls, {
      props: { missionName: '', creatingMission: false },
    })
    const btn = wrapper.findAll('button')[0]
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('shows "Creating..." label when creatingMission prop is true', () => {
    const wrapper = mount(MissionControls, {
      props: { missionName: 'Test', creatingMission: true },
    })
    expect(wrapper.text()).toContain('Creating...')
  })

  it('emits create event on Create Mission click when enabled', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.waypoints = [{ id: '1', lat: 1, lon: 1, blade_on: false, speed: 50 }]

    const wrapper = mount(MissionControls, {
      props: { missionName: 'Test', creatingMission: false },
    })
    await wrapper.vm.$nextTick()
    const createBtn = wrapper.findAll('button')[0]
    await createBtn.trigger('click')
    expect(wrapper.emitted('create')).toBeTruthy()
  })

  it('emits pause/resume/abort events', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.missionStatus = 'running'
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }

    const wrapper = mount(MissionControls, {
      props: { missionName: '', creatingMission: false },
    })
    await wrapper.vm.$nextTick()

    await wrapper.findAll('button')[2].trigger('click') // Pause
    expect(wrapper.emitted('pause')).toBeTruthy()

    ms.missionStatus = 'paused'
    await wrapper.vm.$nextTick()
    await wrapper.findAll('button')[3].trigger('click') // Resume
    expect(wrapper.emitted('resume')).toBeTruthy()

    await wrapper.findAll('button')[4].trigger('click') // Abort
    expect(wrapper.emitted('abort')).toBeTruthy()
  })

  it('Start Mission button is disabled when no current mission', () => {
    const wrapper = mount(MissionControls, {
      props: { missionName: 'Test', creatingMission: false },
    })
    const startBtn = wrapper.findAll('button')[1]
    expect(startBtn.attributes('disabled')).toBeDefined()
  })

  it('emits start event when current mission is set', async () => {
    const { useMissionStore } = await import('@/stores/mission')
    const ms = useMissionStore()
    ms.currentMission = { id: '1', name: 'T', waypoints: [], created_at: '' }

    const wrapper = mount(MissionControls, {
      props: { missionName: 'Test', creatingMission: false, startingMission: false },
    })
    await wrapper.vm.$nextTick()
    const startBtn = wrapper.findAll('button')[1]
    await startBtn.trigger('click')
    expect(wrapper.emitted('start')).toBeTruthy()
  })
})

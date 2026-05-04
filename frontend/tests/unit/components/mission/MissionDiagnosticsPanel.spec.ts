import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const mockDiagnostics = ref(null)
vi.mock('@/composables/useMissionDiagnostics', () => ({
  useMissionDiagnostics: vi.fn(() => ({ diagnostics: mockDiagnostics })),
}))

import MissionDiagnosticsPanel from '@/components/mission/MissionDiagnosticsPanel.vue'
import type { MissionDiagnosticsPayload } from '@/composables/useMissionDiagnostics'

const makeDiagnostics = (overrides: Partial<MissionDiagnosticsPayload> = {}): MissionDiagnosticsPayload => ({
  run_id: 'abcdef1234567890',
  mission_id: 'mission-1',
  blocked_command_count: 0,
  average_pose_quality: 'rtk_fixed',
  heading_alignment_samples: 10,
  pose_update_count: 42,
  ...overrides,
})

describe('MissionDiagnosticsPanel', () => {
  beforeEach(() => {
    mockDiagnostics.value = null
  })

  it('shows placeholder when diagnostics is null', () => {
    const wrapper = mount(MissionDiagnosticsPanel)
    expect(wrapper.find('.placeholder').exists()).toBe(true)
    expect(wrapper.text()).toContain('No active run diagnostics')
    expect(wrapper.find('.panel-title').exists()).toBe(false)
  })

  it('shows Run Quality panel when diagnostics are present', async () => {
    mockDiagnostics.value = makeDiagnostics()
    const wrapper = mount(MissionDiagnosticsPanel)
    expect(wrapper.find('.panel-title').exists()).toBe(true)
    expect(wrapper.text()).toContain('Run Quality')
    expect(wrapper.find('.placeholder').exists()).toBe(false)
  })

  it('applies quality-rtk class for rtk_fixed', async () => {
    mockDiagnostics.value = makeDiagnostics({ average_pose_quality: 'rtk_fixed' })
    const wrapper = mount(MissionDiagnosticsPanel)
    const valueSpan = wrapper.find('.metric-row .value')
    expect(valueSpan.classes()).toContain('quality-rtk')
  })

  it('applies quality-ok class for gps_float', async () => {
    mockDiagnostics.value = makeDiagnostics({ average_pose_quality: 'gps_float' })
    const wrapper = mount(MissionDiagnosticsPanel)
    const valueSpan = wrapper.find('.metric-row .value')
    expect(valueSpan.classes()).toContain('quality-ok')
  })

  it('applies quality-warn class for gps_degraded', async () => {
    mockDiagnostics.value = makeDiagnostics({ average_pose_quality: 'gps_degraded' })
    const wrapper = mount(MissionDiagnosticsPanel)
    const valueSpan = wrapper.find('.metric-row .value')
    expect(valueSpan.classes()).toContain('quality-warn')
  })

  it('applies quality-poor class for unknown quality', async () => {
    mockDiagnostics.value = makeDiagnostics({ average_pose_quality: 'something_unknown' })
    const wrapper = mount(MissionDiagnosticsPanel)
    const valueSpan = wrapper.find('.metric-row .value')
    expect(valueSpan.classes()).toContain('quality-poor')
  })

  it('shows warn class on blocked commands when count > 0', async () => {
    mockDiagnostics.value = makeDiagnostics({ blocked_command_count: 3 })
    const wrapper = mount(MissionDiagnosticsPanel)
    const metricRows = wrapper.findAll('.metric-row')
    const blockedRow = metricRows[3] // 4th metric row: blocked commands
    expect(blockedRow.find('.value').classes()).toContain('warn')
  })

  it('does not show warn class on blocked commands when count is 0', async () => {
    mockDiagnostics.value = makeDiagnostics({ blocked_command_count: 0 })
    const wrapper = mount(MissionDiagnosticsPanel)
    const metricRows = wrapper.findAll('.metric-row')
    const blockedRow = metricRows[3]
    expect(blockedRow.find('.value').classes()).not.toContain('warn')
  })

  it('shows first 8 chars of run_id', async () => {
    mockDiagnostics.value = makeDiagnostics({ run_id: 'abcdef1234567890' })
    const wrapper = mount(MissionDiagnosticsPanel)
    expect(wrapper.find('.run-id .value').text()).toBe('abcdef12')
  })

  it('shows pose_update_count in panel', async () => {
    mockDiagnostics.value = makeDiagnostics({ pose_update_count: 99 })
    const wrapper = mount(MissionDiagnosticsPanel)
    expect(wrapper.text()).toContain('99')
  })

  it('shows heading_alignment_samples in panel', async () => {
    mockDiagnostics.value = makeDiagnostics({ heading_alignment_samples: 7 })
    const wrapper = mount(MissionDiagnosticsPanel)
    expect(wrapper.text()).toContain('7')
  })
})

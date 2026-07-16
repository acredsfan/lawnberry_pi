import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import QualificationStatusPanel from '@/components/mission/QualificationStatusPanel.vue'
import type { QualificationEvidence } from '@/types/autonomyQualification'

function qualification(overrides: Partial<QualificationEvidence> = {}): QualificationEvidence {
  return {
    ok: false,
    reason_codes: ['SUPERVISED_BLADE_TEST_REQUIRED'],
    prerequisite_ok: true,
    prerequisite_reason_codes: [],
    full_autonomy_ok: false,
    full_autonomy_reason_codes: ['SUPERVISED_BLADE_TEST_REQUIRED'],
    camera_ai_safety_role: 'advisory',
    remediation: {
      SUPERVISED_BLADE_TEST_REQUIRED:
        'Complete the bounded supervised blade test and retain accepted evidence.',
    },
    record: {
      schema_version: 2,
      record_id: 'record-prerequisite',
      qualification_level: 'supervised_blade_test_prerequisite',
      status: 'passed',
      stages: [],
    },
    permit: {
      state: 'absent',
      remaining_seconds: 0,
      max_speed_mps: 0,
      max_duration_seconds: 0,
    },
    ...overrides,
  }
}

describe('QualificationStatusPanel', () => {
  it('shows prerequisite, permit, supervised evidence, and full autonomy separately', () => {
    const wrapper = mount(QualificationStatusPanel, {
      props: {
        qualification: qualification({
          permit: {
            state: 'active',
            remaining_seconds: 12.4,
            max_speed_mps: 0.18,
            max_duration_seconds: 20,
          },
        }),
      },
    })

    const text = wrapper.text()
    expect(text).toContain('Prerequisite evidenceAccepted')
    expect(text).toContain('Supervised-test permitActive')
    expect(text).toContain('12.4 s')
    expect(text).toContain('0.18 m/s')
    expect(text).toContain('Supervised blade evidenceRequired')
    expect(text).toContain('Full blade autonomyBlocked')
    expect(text).toContain('SUPERVISED_BLADE_TEST_REQUIRED')
    expect(text).toContain('Camera / AI safety role: Advisory only')
  })

  it('shows artifact-backed supervised evidence only when full autonomy is accepted', () => {
    const wrapper = mount(QualificationStatusPanel, {
      props: {
        qualification: qualification({
          ok: true,
          reason_codes: [],
          full_autonomy_ok: true,
          full_autonomy_reason_codes: [],
          record: {
            schema_version: 2,
            record_id: 'record-full',
            qualification_level: 'full_blade_autonomy',
            status: 'passed',
            stages: [
              {
                stage_id: 'supervised_blade_enabled',
                status: 'passed',
                artifact_ids: ['artifact-supervised'],
              },
            ],
          },
          permit: {
            state: 'completed',
            cleanup_confirmed: true,
            receipt_evidence_eligible: true,
            drive_command_count: 3,
            blade_enable_command_count: 1,
            receipt_id: 'supervised-cleanup-receipt',
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Supervised blade evidenceAccepted')
    expect(wrapper.text()).toContain('Full blade autonomyAuthorized')
    expect(wrapper.text()).toContain(
      'Permit cleanup and artifact-backed supervised evidence are accepted.'
    )
    expect(wrapper.text()).toContain('CleanupConfirmed')
    expect(wrapper.text()).toContain('Receipt evidenceEligible')
    expect(wrapper.text()).toContain('Drive commands3')
    expect(wrapper.text()).toContain('Blade enables1')
  })

  it('fails closed for legacy responses and retains terminal permit errors', () => {
    const wrapper = mount(QualificationStatusPanel, {
      props: {
        qualification: qualification({
          prerequisite_ok: undefined,
          full_autonomy_ok: undefined,
          camera_ai_safety_role: undefined,
          record: {
            schema_version: 1,
            record_id: 'legacy-record',
            status: 'passed',
            stages: [],
          },
          permit: {
            state: 'expired',
            terminal_reason_code: 'SUPERVISED_TEST_PERMIT_EXPIRED',
          },
        }),
        retainedTerminalErrors: [
          {
            code: 'SUPERVISED_TEST_PERMIT_EXPIRED',
            detail: 'Request a new permit after operator review.',
          },
        ],
      },
    })

    const text = wrapper.text()
    expect(text).toContain('Prerequisite evidenceBlocked')
    expect(text).toContain('Legacy schema-v1 evidence cannot authorize')
    expect(text).toContain('Supervised-test permitExpired')
    expect(text).toContain('This permit is terminal and cannot be reused.')
    expect(text).toContain('Retained qualification errors')
    expect(text).toContain('SUPERVISED_TEST_PERMIT_EXPIRED')
    expect(text).toContain('Camera / AI safety role: Unknown; non-authorizing')
  })

  it('is status-only and exposes no permit or actuation controls', () => {
    const wrapper = mount(QualificationStatusPanel, {
      props: { qualification: qualification() },
    })

    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(wrapper.findAll('input')).toHaveLength(0)
    expect(wrapper.findAll('form')).toHaveLength(0)
  })
})

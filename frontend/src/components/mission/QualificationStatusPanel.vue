<template>
  <div class="qualification-status" aria-live="polite">
    <div class="qualification-grid" data-testid="qualification-stage-grid">
      <article class="qualification-stage">
        <div class="qualification-stage__header">
          <span>Prerequisite evidence</span>
          <span :class="['qualification-pill', prerequisiteTone]">{{ prerequisiteLabel }}</span>
        </div>
        <p>{{ prerequisiteDetail }}</p>
        <ReasonList :codes="prerequisiteReasons" :remediation="qualification?.remediation" />
      </article>

      <article class="qualification-stage">
        <div class="qualification-stage__header">
          <span>Supervised-test permit</span>
          <span :class="['qualification-pill', permitTone]">{{ permitLabel }}</span>
        </div>
        <p>{{ permitDetail }}</p>
        <dl v-if="permitState === 'completed'" class="permit-bounds permit-bounds--outcome">
          <div>
            <dt>Cleanup</dt>
            <dd>{{ qualification?.permit?.cleanup_confirmed === true ? 'Confirmed' : 'Unconfirmed' }}</dd>
          </div>
          <div>
            <dt>Receipt evidence</dt>
            <dd>
              {{ qualification?.permit?.receipt_evidence_eligible === true ? 'Eligible' : 'Not eligible' }}
            </dd>
          </div>
        </dl>
        <dl v-if="hasPermitBounds" class="permit-bounds">
          <div>
            <dt>Remaining</dt>
            <dd>{{ formattedRemaining }}</dd>
          </div>
          <div>
            <dt>Maximum speed</dt>
            <dd>{{ formatNumber(qualification?.permit?.max_speed_mps) }} m/s</dd>
          </div>
          <div>
            <dt>Maximum duration</dt>
            <dd>{{ formatNumber(qualification?.permit?.max_duration_seconds) }} s</dd>
          </div>
        </dl>
        <dl v-if="permitState !== 'absent'" class="permit-bounds permit-bounds--commands">
          <div>
            <dt>Drive commands</dt>
            <dd>{{ formatCount(qualification?.permit?.drive_command_count) }}</dd>
          </div>
          <div>
            <dt>Blade enables</dt>
            <dd>{{ formatCount(qualification?.permit?.blade_enable_command_count) }}</dd>
          </div>
        </dl>
      </article>

      <article class="qualification-stage">
        <div class="qualification-stage__header">
          <span>Supervised blade evidence</span>
          <span :class="['qualification-pill', supervisedTone]">{{ supervisedLabel }}</span>
        </div>
        <p>{{ supervisedDetail }}</p>
        <ReasonList :codes="supervisedReasons" :remediation="qualification?.remediation" />
      </article>

      <article class="qualification-stage">
        <div class="qualification-stage__header">
          <span>Full blade autonomy</span>
          <span :class="['qualification-pill', fullAutonomyTone]">{{ fullAutonomyLabel }}</span>
        </div>
        <p>{{ fullAutonomyDetail }}</p>
        <ReasonList :codes="fullAutonomyReasons" :remediation="qualification?.remediation" />
      </article>
    </div>

    <div class="camera-role" data-testid="camera-ai-safety-role">
      <strong>Camera / AI safety role: {{ cameraRoleLabel }}</strong>
      <span>Camera perception does not replace independent ToF, geofence, or live-safety stops.</span>
    </div>

    <div v-if="retainedTerminalErrors.length" class="terminal-errors" role="alert">
      <strong>Retained qualification errors</strong>
      <ul>
        <li v-for="terminalError in retainedTerminalErrors" :key="terminalError.code">
          <code>{{ terminalError.code }}</code>
          <span v-if="terminalError.detail">{{ terminalError.detail }}</span>
        </li>
      </ul>
    </div>

    <p v-if="error" class="qualification-fetch-error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
  import { computed, defineComponent, h, type PropType } from 'vue'
  import type {
    QualificationEvidence,
    QualificationTerminalError,
  } from '@/types/autonomyQualification'

  const props = withDefaults(
    defineProps<{
      qualification: QualificationEvidence | null
      retainedTerminalErrors?: QualificationTerminalError[]
      error?: string
    }>(),
    {
      retainedTerminalErrors: () => [],
      error: '',
    }
  )

  const ReasonList = defineComponent({
    name: 'QualificationReasonList',
    props: {
      codes: { type: Array as PropType<string[]>, required: true },
      remediation: {
        type: Object as PropType<Record<string, string> | undefined>,
        default: undefined,
      },
    },
    setup(reasonProps) {
      return () =>
        reasonProps.codes.length
          ? h(
              'ul',
              { class: 'qualification-reasons' },
              reasonProps.codes.map((code) =>
                h('li', { key: code }, [
                  h('code', code),
                  ...(reasonProps.remediation?.[code]
                    ? [h('span', reasonProps.remediation[code])]
                    : []),
                ])
              )
            )
          : null
    },
  })

  function unique(codes: Array<string | null | undefined>): string[] {
    return [...new Set(codes.filter((code): code is string => Boolean(code)))]
  }

  const prerequisiteReasons = computed(() =>
    unique(props.qualification?.prerequisite_reason_codes ?? [])
  )
  const fullAutonomyReasons = computed(() =>
    unique(
      props.qualification?.full_autonomy_reason_codes ?? props.qualification?.reason_codes ?? []
    )
  )
  const supervisedStage = computed(() =>
    props.qualification?.record?.stages?.find(
      (stage) => stage.stage_id === 'supervised_blade_enabled'
    )
  )
  const supervisedReasons = computed(() => {
    const stage = supervisedStage.value
    return unique([
      stage?.reason_code,
      ...fullAutonomyReasons.value.filter(
        (code) => code.startsWith('SUPERVISED_') || code === 'QUALIFICATION_STAGE_ARTIFACT_INVALID'
      ),
    ])
  })

  const prerequisiteLabel = computed(() =>
    props.qualification?.prerequisite_ok === true ? 'Accepted' : 'Blocked'
  )
  const prerequisiteTone = computed(() =>
    props.qualification?.prerequisite_ok === true ? 'accepted' : 'blocked'
  )
  const prerequisiteDetail = computed(() => {
    if (props.qualification?.prerequisite_ok === true) {
      return 'Current schema-v2 blade-off evidence satisfies the supervised-test prerequisite.'
    }
    const schemaVersion = props.qualification?.record?.schema_version
    if (schemaVersion && schemaVersion < 2) {
      return `Legacy schema-v${schemaVersion} evidence cannot authorize the supervised test or full autonomy.`
    }
    return 'The supervised blade test remains unavailable until all prerequisite evidence is current.'
  })

  const permitState = computed(() => props.qualification?.permit?.state ?? 'absent')
  const permitLabel = computed(() => {
    const labels: Record<string, string> = {
      absent: 'Not issued',
      issued: 'Issued',
      active: 'Active',
      completed: 'Completed',
      revoked: 'Revoked',
      expired: 'Expired',
    }
    return labels[permitState.value] ?? 'Unavailable'
  })
  const permitTone = computed(() => {
    if (permitState.value === 'active') return 'active'
    if (permitState.value === 'issued') return 'pending'
    if (permitState.value === 'completed') {
      return props.qualification?.permit?.cleanup_confirmed === true &&
        props.qualification?.permit?.receipt_evidence_eligible === true
        ? 'accepted'
        : 'blocked'
    }
    if (['revoked', 'expired'].includes(permitState.value)) return 'blocked'
    return 'neutral'
  })
  const permitDetail = computed(() => {
    if (permitState.value === 'active') {
      return 'A qualification-only permit is active; it does not authorize ordinary or scheduled missions.'
    }
    if (permitState.value === 'issued') {
      return 'The one-purpose permit is awaiting activation by the authenticated local operator workflow.'
    }
    if (permitState.value === 'completed') {
      if (
        props.qualification?.permit?.cleanup_confirmed !== true ||
        props.qualification?.permit?.receipt_evidence_eligible !== true
      ) {
        return 'The permit is complete, but cleanup or receipt eligibility is not confirmed.'
      }
      return props.qualification?.full_autonomy_ok === true
        ? 'Permit cleanup and artifact-backed supervised evidence are accepted.'
        : 'Cleanup completed; artifact-backed supervised evidence must still be accepted for full autonomy.'
    }
    if (['revoked', 'expired'].includes(permitState.value)) {
      return 'This permit is terminal and cannot be reused.'
    }
    if (props.qualification?.prerequisite_ok === true) {
      return 'No permit is active. Permit issuance remains outside this status-only interface.'
    }
    return 'No permit is active, and prerequisite evidence is not yet accepted.'
  })
  const hasPermitBounds = computed(() => ['issued', 'active'].includes(permitState.value))
  const formattedRemaining = computed(() => {
    const remaining = props.qualification?.permit?.remaining_seconds
    return typeof remaining === 'number' && Number.isFinite(remaining)
      ? `${Math.max(0, remaining).toFixed(1)} s`
      : 'Unavailable'
  })

  const supervisedLabel = computed(() => {
    const status = supervisedStage.value?.status
    if (status === 'passed') {
      return props.qualification?.full_autonomy_ok === true ? 'Accepted' : 'Unaccepted'
    }
    if (status === 'failed') return 'Failed'
    if (status === 'interrupted') return 'Interrupted'
    if (status === 'operator_required') return 'Operator required'
    if (status === 'skipped') return 'Not completed'
    return 'Required'
  })
  const supervisedTone = computed(() => {
    if (supervisedLabel.value === 'Accepted') return 'accepted'
    if (['Required', 'Not completed', 'Operator required'].includes(supervisedLabel.value)) {
      return 'pending'
    }
    return 'blocked'
  })
  const supervisedDetail = computed(() => {
    if (supervisedLabel.value === 'Accepted') {
      return 'Current artifact-backed supervised blade evidence and confirmed cleanup are accepted.'
    }
    if (supervisedStage.value?.status === 'passed') {
      return 'A recorded pass is present but its context, artifact, or cleanup receipt is not accepted.'
    }
    return 'A bounded physical supervised blade test is required before ordinary blade autonomy.'
  })

  const fullAutonomyLabel = computed(() =>
    props.qualification?.full_autonomy_ok === true ? 'Authorized' : 'Blocked'
  )
  const fullAutonomyTone = computed(() =>
    props.qualification?.full_autonomy_ok === true ? 'accepted' : 'blocked'
  )
  const fullAutonomyDetail = computed(() =>
    props.qualification?.full_autonomy_ok === true
      ? 'Current context-bound evidence authorizes ordinary blade missions and scheduled mowing.'
      : 'Ordinary blade commands, missions, and schedules remain prohibited.'
  )

  const cameraRoleLabel = computed(() =>
    props.qualification?.camera_ai_safety_role === 'advisory'
      ? 'Advisory only'
      : 'Unknown; non-authorizing'
  )

  function formatNumber(value: number | undefined): string {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : 'Unavailable'
  }

  function formatCount(value: number | undefined): string {
    return typeof value === 'number' && Number.isInteger(value) && value >= 0
      ? String(value)
      : 'Unavailable'
  }
</script>

<style scoped>
  .qualification-status {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .qualification-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.65rem;
  }

  .qualification-stage {
    min-width: 0;
    padding: 0.7rem;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.035);
  }

  .qualification-stage__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    font-weight: 600;
  }

  .qualification-stage p {
    margin: 0.45rem 0 0;
    color: rgba(255, 255, 255, 0.72);
    font-size: 0.86rem;
  }

  .qualification-pill {
    flex-shrink: 0;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 999px;
    padding: 0.15rem 0.45rem;
    font-size: 0.72rem;
  }

  .qualification-pill.accepted {
    color: #86efac;
    border-color: rgba(134, 239, 172, 0.45);
  }
  .qualification-pill.active {
    color: #67e8f9;
    border-color: rgba(103, 232, 249, 0.5);
  }
  .qualification-pill.pending {
    color: #fde68a;
    border-color: rgba(253, 230, 138, 0.45);
  }
  .qualification-pill.blocked {
    color: #fca5a5;
    border-color: rgba(252, 165, 165, 0.45);
  }
  .qualification-pill.neutral {
    color: #cbd5e1;
  }

  :deep(.qualification-reasons),
  .terminal-errors ul {
    margin: 0.5rem 0 0;
    padding-left: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  :deep(.qualification-reasons li),
  .terminal-errors li {
    font-size: 0.8rem;
  }

  :deep(.qualification-reasons code),
  .terminal-errors code {
    overflow-wrap: anywhere;
  }

  :deep(.qualification-reasons span),
  .terminal-errors span {
    display: block;
    margin-top: 0.1rem;
    color: rgba(255, 255, 255, 0.72);
  }

  .permit-bounds {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.35rem;
    margin: 0.55rem 0 0;
  }

  .permit-bounds div {
    min-width: 0;
  }

  .permit-bounds dt {
    color: rgba(255, 255, 255, 0.58);
    font-size: 0.7rem;
  }

  .permit-bounds dd {
    margin: 0.1rem 0 0;
    font-size: 0.8rem;
  }

  .camera-role,
  .terminal-errors {
    padding: 0.65rem;
    border-radius: 6px;
  }

  .camera-role {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    border: 1px solid rgba(103, 232, 249, 0.3);
    background: rgba(8, 145, 178, 0.08);
  }

  .camera-role span {
    color: rgba(255, 255, 255, 0.72);
    font-size: 0.84rem;
  }

  .terminal-errors {
    border: 1px solid rgba(252, 165, 165, 0.45);
    background: rgba(127, 29, 29, 0.18);
    color: #fecaca;
  }

  .qualification-fetch-error {
    margin: 0;
    color: #fca5a5;
  }

  @media (max-width: 640px) {
    .permit-bounds {
      grid-template-columns: 1fr;
    }
  }
</style>

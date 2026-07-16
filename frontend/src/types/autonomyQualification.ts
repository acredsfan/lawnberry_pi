export interface ReadinessCheck {
  code: string
  remediation?: string
}

export interface AutonomyReadinessReport {
  ready?: boolean
  blocking_reason_codes?: string[]
  checks?: ReadinessCheck[]
}

export interface QualificationStageResult {
  stage_id: string
  status: 'passed' | 'failed' | 'interrupted' | 'skipped' | 'operator_required' | string
  reason_code?: string | null
  summary?: string
  artifact_ids?: string[]
}

export interface QualificationRecord {
  schema_version?: number
  record_id?: string
  qualification_level?:
    | 'blade_off_diagnostic'
    | 'supervised_blade_test_prerequisite'
    | 'full_blade_autonomy'
    | string
  status?: string
  stages?: QualificationStageResult[]
}

export interface SupervisedTestPermitStatus {
  state?: 'absent' | 'issued' | 'active' | 'completed' | 'revoked' | 'expired' | string
  permit_id_hash?: string | null
  qualification_record_id?: string | null
  issued_at?: string | null
  activated_at?: string | null
  expires_at?: string | null
  remaining_seconds?: number
  max_speed_mps?: number
  max_duration_seconds?: number
  intervention_confirmed?: boolean
  cleanup_confirmed?: boolean
  receipt_evidence_eligible?: boolean
  drive_command_count?: number
  blade_enable_command_count?: number
  terminal_reason_code?: string | null
  receipt_id?: string | null
}

export interface QualificationEvidence {
  ok?: boolean
  reason_codes?: string[]
  remediation?: Record<string, string>
  requested_level?: string
  available_level?: string | null
  prerequisite_ok?: boolean
  prerequisite_reason_codes?: string[]
  full_autonomy_ok?: boolean
  full_autonomy_reason_codes?: string[]
  camera_ai_safety_role?: string
  record?: QualificationRecord | null
  permit?: SupervisedTestPermitStatus | null
}

export interface QualificationTerminalError {
  code: string
  detail?: string
}

export function collectQualificationTerminalErrors(
  qualification: QualificationEvidence | null
): QualificationTerminalError[] {
  if (!qualification) return []

  const errors = new Map<string, QualificationTerminalError>()
  const permitReason = qualification.permit?.terminal_reason_code
  if (permitReason) {
    errors.set(permitReason, {
      code: permitReason,
      detail: qualification.remediation?.[permitReason],
    })
  }

  for (const stage of qualification.record?.stages ?? []) {
    if (!['failed', 'interrupted'].includes(stage.status)) continue
    const code =
      stage.reason_code || `${stage.stage_id.toUpperCase()}_${stage.status.toUpperCase()}`
    errors.set(code, {
      code,
      detail: qualification.remediation?.[code] || stage.summary,
    })
  }
  return [...errors.values()]
}

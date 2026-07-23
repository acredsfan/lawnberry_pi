import type { BoundaryVerificationPoint, BoundaryVerificationSession } from '@/services/mapsClient'

const PROBLEM_STATUSES = new Set<BoundaryVerificationPoint['status']>(['failed', 'interrupted'])

export function activeBoundaryVerificationPoint(
  session: BoundaryVerificationSession | null | undefined
): BoundaryVerificationPoint | null {
  if (session?.target_index == null) return null
  return session.points.find((point) => point.index === session.target_index) ?? null
}

export function latestBoundaryVerificationProblem(
  session: BoundaryVerificationSession | null | undefined
): BoundaryVerificationPoint | null {
  if (!session || session.status === 'cancelled') return null
  return [...session.points].reverse().find((point) => PROBLEM_STATUSES.has(point.status)) ?? null
}

export function boundaryVerificationFailureKey(
  point: BoundaryVerificationPoint | null | undefined
): string | null {
  if (!point || !PROBLEM_STATUSES.has(point.status)) return null
  if (point.mission_id) return `mission:${point.mission_id}`
  return `point:${point.index}:${point.status}:${point.error ?? ''}`
}

export function boundaryVerificationStatusLabel(
  point: BoundaryVerificationPoint | null | undefined
): string | null {
  if (!point) return null
  if (point.status === 'starting' && point.mission_phase === 'heading_bootstrap') {
    return 'heading bootstrap'
  }
  if (point.status === 'starting' && point.mission_phase === 'heading_validation') {
    return 'validating heading'
  }
  return point.status
}

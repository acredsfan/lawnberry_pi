import { describe, expect, it } from 'vitest'

import {
  activeBoundaryVerificationPoint,
  boundaryVerificationFailureKey,
  boundaryVerificationStatusLabel,
  latestBoundaryVerificationProblem,
} from '@/utils/boundaryVerification'
import type { BoundaryVerificationSession } from '@/services/mapsClient'

function session(
  overrides: Partial<BoundaryVerificationSession> = {}
): BoundaryVerificationSession {
  return {
    status: 'active',
    target_index: null,
    points: [],
    ...overrides,
  }
}

describe('boundary verification status helpers', () => {
  it('keeps a failed point visible after target_index clears', () => {
    const failed = {
      index: 0,
      reference: { latitude: 40, longitude: -75 },
      approach: { latitude: 40.0001, longitude: -75 },
      status: 'failed' as const,
      mission_id: 'mission-1',
      error: 'HEADING_ALIGNMENT_REQUIRED',
    }
    const value = session({ points: [failed] })

    expect(activeBoundaryVerificationPoint(value)).toBeNull()
    expect(latestBoundaryVerificationProblem(value)).toEqual(failed)
  })

  it('uses mission identity so a repeated blocker produces one new notice per attempt', () => {
    const first = {
      index: 0,
      reference: { latitude: 40, longitude: -75 },
      approach: { latitude: 40.0001, longitude: -75 },
      status: 'failed' as const,
      mission_id: 'mission-1',
      error: 'HEADING_ALIGNMENT_REQUIRED',
    }
    const retry = { ...first, mission_id: 'mission-2' }

    const firstKey = boundaryVerificationFailureKey(first)
    expect(boundaryVerificationFailureKey(first)).toBe(firstKey)
    expect(firstKey).not.toBe(boundaryVerificationFailureKey(retry))
  })

  it('does not label heading admission as point travel', () => {
    const point = {
      index: 0,
      reference: { latitude: 40, longitude: -75 },
      approach: { latitude: 40.0001, longitude: -75 },
      status: 'starting' as const,
      mission_phase: 'heading_bootstrap',
      heading_bootstrap_required: true,
    }

    expect(boundaryVerificationStatusLabel(point)).toBe('heading bootstrap')
    expect(boundaryVerificationStatusLabel({ ...point, mission_phase: 'heading_validation' })).toBe(
      'validating heading'
    )
  })
})

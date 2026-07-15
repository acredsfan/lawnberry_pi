import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlanningStore } from '@/stores/planning'
import * as planningClient from '@/services/planningClient'

vi.mock('@/services/planningClient', () => ({
  getPlanningJobs: vi.fn(),
  createPlanningJob: vi.fn(),
  deletePlanningJob: vi.fn(),
  startPlanningJob: vi.fn(),
  pausePlanningJob: vi.fn(),
  resumePlanningJob: vi.fn(),
  cancelPlanningJob: vi.fn(),
  getSchedules: vi.fn(),
  createSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
  enableSchedule: vi.fn(),
  disableSchedule: vi.fn(),
}))

const planningJob = (status: string) =>
  ({
    id: 'job-1',
    name: 'Front and back',
    zones: ['front', 'back'],
    status,
    enabled: true,
    priority: 1,
  }) as any

describe('planning store authoritative controls', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('applies only the state returned by a successful server action', async () => {
    const store = usePlanningStore()
    store.jobs = [planningJob('pending')]
    vi.mocked(planningClient.startPlanningJob).mockResolvedValue(planningJob('running'))
    vi.mocked(planningClient.pausePlanningJob).mockResolvedValue(planningJob('paused'))

    await store.startJob('job-1')
    expect(store.jobs[0].status).toBe('running')

    await store.pauseJob('job-1')
    expect(store.jobs[0].status).toBe('paused')
  })

  it('preserves the last confirmed state when a control request fails', async () => {
    const store = usePlanningStore()
    store.jobs = [planningJob('running')]
    vi.mocked(planningClient.pausePlanningJob).mockRejectedValue(new Error('pause rejected'))

    await expect(store.pauseJob('job-1')).rejects.toThrow('pause rejected')
    expect(store.jobs[0].status).toBe('running')
  })

  it('keeps a cancelled job visible with the server-confirmed terminal state', async () => {
    const store = usePlanningStore()
    store.jobs = [planningJob('running')]
    vi.mocked(planningClient.cancelPlanningJob).mockResolvedValue(planningJob('cancelled'))

    await store.cancelJob('job-1')

    expect(store.jobs).toHaveLength(1)
    expect(store.jobs[0].status).toBe('cancelled')
  })
})

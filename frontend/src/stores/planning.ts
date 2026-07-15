import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useWebSocket } from '@/services/websocket'
import {
  getPlanningJobs,
  createPlanningJob,
  deletePlanningJob,
  startPlanningJob,
  pausePlanningJob,
  resumePlanningJob,
  cancelPlanningJob,
  getSchedules,
  createSchedule as apiCreateSchedule,
  deleteSchedule as apiDeleteSchedule,
  enableSchedule,
  disableSchedule,
  getPlanningCapabilities,
} from '@/services/planningClient'
import type { PlanningCapabilities, PlanningJob } from '@/services/planningClient'
import { getMapZones } from '@/services/mapsClient'
import type { Zone } from '@/services/mapsClient'

export type { PlanningJob, Zone }

export const usePlanningStore = defineStore('planning', () => {
  const jobs = ref<PlanningJob[]>([])
  const schedules = ref<PlanningJob[]>([])
  const zones = ref<Zone[]>([])
  const capabilities = ref<PlanningCapabilities | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const { subscribe } = useWebSocket()

  async function fetchJobs(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      jobs.value = await getPlanningJobs()
    } catch (err) {
      error.value = (err as { message?: string })?.message ?? 'Failed to load planning jobs'
    } finally {
      loading.value = false
    }
  }

  async function createJob(data: Record<string, unknown>): Promise<PlanningJob> {
    const job = await createPlanningJob(data)
    jobs.value.push(job)
    return job
  }

  async function deleteJob(id: string): Promise<void> {
    await deletePlanningJob(id)
    jobs.value = jobs.value.filter((j) => j.id !== id)
  }

  function applyJob(updated: PlanningJob): PlanningJob {
    const idx = jobs.value.findIndex((job) => job.id === updated.id)
    if (idx === -1) {
      jobs.value.push(updated)
    } else {
      jobs.value[idx] = updated
    }
    return updated
  }

  async function startJob(id: string): Promise<PlanningJob> {
    return applyJob(await startPlanningJob(id))
  }

  async function pauseJob(id: string): Promise<PlanningJob> {
    return applyJob(await pausePlanningJob(id))
  }

  async function resumeJob(id: string): Promise<PlanningJob> {
    return applyJob(await resumePlanningJob(id))
  }

  async function cancelJob(id: string): Promise<PlanningJob> {
    return applyJob(await cancelPlanningJob(id))
  }

  async function enableJob(id: string): Promise<void> {
    const updated = await enableSchedule(id)
    const idx = jobs.value.findIndex((j) => j.id === id)
    if (idx !== -1) {
      jobs.value[idx] = updated
    }
  }

  async function disableJob(id: string): Promise<void> {
    const updated = await disableSchedule(id)
    const idx = jobs.value.findIndex((j) => j.id === id)
    if (idx !== -1) {
      jobs.value[idx] = updated
    }
  }

  // ---- Schedule actions (/api/v2/schedules) ----

  async function fetchSchedules(): Promise<void> {
    try {
      schedules.value = await getSchedules()
    } catch (err) {
      error.value = (err as { message?: string })?.message ?? 'Failed to load schedules'
    }
  }

  async function createSchedule(data: Record<string, unknown>): Promise<PlanningJob> {
    const schedule = await apiCreateSchedule(data)
    schedules.value.push(schedule)
    return schedule
  }

  async function deleteSchedule(id: string): Promise<void> {
    await apiDeleteSchedule(id)
    schedules.value = schedules.value.filter((s) => s.id !== id)
  }

  async function enableScheduleById(id: string): Promise<void> {
    const updated = await enableSchedule(id)
    const idx = schedules.value.findIndex((s) => s.id === id)
    if (idx !== -1) {
      schedules.value[idx] = updated
    }
  }

  async function disableScheduleById(id: string): Promise<void> {
    const updated = await disableSchedule(id)
    const idx = schedules.value.findIndex((s) => s.id === id)
    if (idx !== -1) {
      schedules.value[idx] = updated
    }
  }

  async function fetchZones(): Promise<void> {
    try {
      zones.value = await getMapZones()
    } catch (err) {
      error.value = (err as { message?: string })?.message ?? 'Failed to load zones'
    }
  }

  async function fetchCapabilities(): Promise<void> {
    try {
      capabilities.value = await getPlanningCapabilities()
    } catch (err) {
      capabilities.value = null
      error.value = (err as { message?: string })?.message ?? 'Planning capabilities unavailable'
    }
  }

  // Auto-refresh on relevant WebSocket events
  subscribe('planning.zone.changed', () => void fetchJobs())
  subscribe('planning.schedule.fired', () => void fetchJobs())

  return {
    jobs,
    schedules,
    zones,
    capabilities,
    loading,
    error,
    fetchJobs,
    createJob,
    deleteJob,
    startJob,
    pauseJob,
    resumeJob,
    cancelJob,
    enableJob,
    disableJob,
    fetchSchedules,
    createSchedule,
    deleteSchedule,
    enableScheduleById,
    disableScheduleById,
    fetchZones,
    fetchCapabilities,
  }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useWebSocket } from '@/services/websocket'
import {
  getPlanningJobs,
  createPlanningJob,
  deletePlanningJob,
  getSchedules,
  createSchedule as apiCreateSchedule,
  deleteSchedule as apiDeleteSchedule,
  enableSchedule,
  disableSchedule,
} from '@/services/planningClient'
import type { PlanningJob } from '@/services/planningClient'

export type { PlanningJob }

export const usePlanningStore = defineStore('planning', () => {
  const jobs = ref<PlanningJob[]>([])
  const schedules = ref<PlanningJob[]>([])
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
    jobs.value = jobs.value.filter(j => j.id !== id)
  }

  async function enableJob(id: string): Promise<void> {
    const updated = await enableSchedule(id)
    const idx = jobs.value.findIndex(j => j.id === id)
    if (idx !== -1) {
      jobs.value[idx] = updated
    }
  }

  async function disableJob(id: string): Promise<void> {
    const updated = await disableSchedule(id)
    const idx = jobs.value.findIndex(j => j.id === id)
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
    schedules.value = schedules.value.filter(s => s.id !== id)
  }

  async function enableScheduleById(id: string): Promise<void> {
    const updated = await enableSchedule(id)
    const idx = schedules.value.findIndex(s => s.id === id)
    if (idx !== -1) {
      schedules.value[idx] = updated
    }
  }

  async function disableScheduleById(id: string): Promise<void> {
    const updated = await disableSchedule(id)
    const idx = schedules.value.findIndex(s => s.id === id)
    if (idx !== -1) {
      schedules.value[idx] = updated
    }
  }

  // Auto-refresh on relevant WebSocket events
  subscribe('planning.zone.changed', () => void fetchJobs())
  subscribe('planning.schedule.fired', () => void fetchJobs())

  return {
    jobs,
    schedules,
    loading,
    error,
    fetchJobs,
    createJob,
    deleteJob,
    enableJob,
    disableJob,
    fetchSchedules,
    createSchedule,
    deleteSchedule,
    enableScheduleById,
    disableScheduleById,
  }
})

/**
 * planningClient.ts — typed client for /api/v2/planning/jobs and /api/v2/schedules
 *
 * All request and response types come from the generated api.ts (PlanningJobResponse).
 * Import from this module instead of calling apiService directly in Vue components.
 */
import apiService from './api'
import type { components } from '@/types/api'

// Re-export from generated types
export type PlanningJob = components['schemas']['PlanningJobResponse']

// ---- Planning jobs (/api/v2/planning/jobs) ----

export async function getPlanningJobs(): Promise<PlanningJob[]> {
  const response = await apiService.get<PlanningJob[]>('/api/v2/planning/jobs')
  return response.data
}

export async function createPlanningJob(data: Record<string, unknown>): Promise<PlanningJob> {
  const response = await apiService.post<PlanningJob>('/api/v2/planning/jobs', data)
  return response.data
}

export async function deletePlanningJob(id: string): Promise<void> {
  await apiService.delete(`/api/v2/planning/jobs/${id}`)
}

// ---- Schedules (/api/v2/schedules) ----

export async function getSchedules(): Promise<PlanningJob[]> {
  const response = await apiService.get<PlanningJob[]>('/api/v2/schedules')
  return response.data
}

export async function createSchedule(data: Record<string, unknown>): Promise<PlanningJob> {
  const response = await apiService.post<PlanningJob>('/api/v2/schedules', data)
  return response.data
}

export async function updateSchedule(id: string, data: Record<string, unknown>): Promise<PlanningJob> {
  const response = await apiService.put<PlanningJob>(`/api/v2/schedules/${id}`, data)
  return response.data
}

export async function deleteSchedule(id: string): Promise<void> {
  await apiService.delete(`/api/v2/schedules/${id}`)
}

export async function enableSchedule(id: string): Promise<PlanningJob> {
  const response = await apiService.post<PlanningJob>(`/api/v2/schedules/${id}/enable`)
  return response.data
}

export async function disableSchedule(id: string): Promise<PlanningJob> {
  const response = await apiService.post<PlanningJob>(`/api/v2/schedules/${id}/disable`)
  return response.data
}

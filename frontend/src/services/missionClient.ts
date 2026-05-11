/**
 * missionClient.ts — typed client for /api/v2/missions/*
 *
 * All request and response types come from the generated api.ts.
 * Import from this module instead of calling apiService directly in Vue components.
 */
import apiService from './api'
import type { components } from '@/types/api'

// Convenience aliases derived from generated types
export type Mission = components['schemas']['Mission']
export type MissionCreationRequest = components['schemas']['MissionCreationRequest']
export type MissionStatus = components['schemas']['MissionStatus']

export async function createMission(
  request: MissionCreationRequest
): Promise<Mission> {
  const response = await apiService.post<Mission>('/api/v2/missions/create', request)
  return response.data
}

export async function startMission(missionId: string): Promise<{ status: string }> {
  const response = await apiService.post<{ status: string }>(
    `/api/v2/missions/${missionId}/start`
  )
  return response.data
}

export async function pauseMission(missionId: string): Promise<{ status: string }> {
  const response = await apiService.post<{ status: string }>(
    `/api/v2/missions/${missionId}/pause`
  )
  return response.data
}

export async function resumeMission(missionId: string): Promise<{ status: string }> {
  const response = await apiService.post<{ status: string }>(
    `/api/v2/missions/${missionId}/resume`
  )
  return response.data
}

export async function abortMission(missionId: string): Promise<{ status: string }> {
  const response = await apiService.post<{ status: string }>(
    `/api/v2/missions/${missionId}/abort`
  )
  return response.data
}

export async function getMissionStatus(missionId: string): Promise<MissionStatus> {
  const response = await apiService.get<MissionStatus>(
    `/api/v2/missions/${missionId}/status`
  )
  return response.data
}

export async function getMission(missionId: string): Promise<Mission> {
  const response = await apiService.get<Mission>(`/api/v2/missions/${missionId}`)
  return response.data
}

export async function listMissions(): Promise<Mission[]> {
  const response = await apiService.get<Mission[]>('/api/v2/missions/list')
  return response.data
}

export async function updateMission(
  id: string,
  payload: { name?: string; waypoints?: components['schemas']['MissionWaypoint'][] }
): Promise<Mission> {
  const response = await apiService.patch<Mission>(`/api/v2/missions/${id}`, payload)
  return response.data
}

export async function deleteMission(id: string): Promise<void> {
  await apiService.delete(`/api/v2/missions/${id}`)
}

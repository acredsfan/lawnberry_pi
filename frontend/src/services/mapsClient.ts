/**
 * mapsClient.ts — typed client for /api/v2/map/* and /api/v2/planning/*
 *
 * Replaces ApiService methods for maps and planning management.
 */
import apiService from './api'
import type { components } from '@/types/api'

export type Zone = components['schemas']['Zone']
export type MapLocations = components['schemas']['MapLocations']

// MapConfiguration and PlanningJob types are not defined in generated schemas,
// so we use unknown and let callers cast or type them at the call site.
export type MapConfiguration = unknown
export type PlanningJob = unknown

export async function getMapZones(): Promise<Zone[]> {
  const response = await apiService.get<Zone[]>('/api/v2/map/zones')
  return response.data
}

export async function postMapZones(zones: Zone[]): Promise<Zone[]> {
  const response = await apiService.post<Zone[]>('/api/v2/map/zones', zones)
  return response.data
}

export async function getMapLocations(): Promise<MapLocations> {
  const response = await apiService.get<MapLocations>('/api/v2/map/locations')
  return response.data
}

export async function putMapLocations(locations: MapLocations): Promise<MapLocations> {
  const response = await apiService.put<MapLocations>('/api/v2/map/locations', locations)
  return response.data
}

export interface GetMapConfigurationParams {
  config_id?: string
  simulate_fallback?: string | null
}

export async function getMapConfiguration(
  params?: GetMapConfigurationParams
): Promise<MapConfiguration> {
  const query = new URLSearchParams()
  if (params) {
    if (params.config_id) query.append('config_id', params.config_id)
    if (params.simulate_fallback) query.append('simulate_fallback', params.simulate_fallback)
  }
  const qs = query.toString()
  const response = await apiService.get<MapConfiguration>(
    `/api/v2/map/configuration${qs ? `?${qs}` : ''}`
  )
  return response.data
}

export interface SaveMapConfigurationParams {
  config_id?: string
}

export async function saveMapConfiguration(
  configuration: unknown,
  params?: SaveMapConfigurationParams
): Promise<MapConfiguration> {
  const query = new URLSearchParams()
  if (params?.config_id) query.append('config_id', params.config_id)
  const qs = query.toString()
  const response = await apiService.put<MapConfiguration>(
    `/api/v2/map/configuration${qs ? `?${qs}` : ''}`,
    configuration
  )
  return response.data
}

export interface TriggerMapProviderFallbackParams {
  config_id?: string
}

export async function triggerMapProviderFallback(
  params?: TriggerMapProviderFallbackParams
): Promise<MapConfiguration> {
  const query = new URLSearchParams()
  if (params?.config_id) query.append('config_id', params.config_id)
  const qs = query.toString()
  const response = await apiService.post<MapConfiguration>(
    `/api/v2/map/provider-fallback${qs ? `?${qs}` : ''}`,
    {}
  )
  return response.data
}

export async function listPlanningJobs(): Promise<PlanningJob[]> {
  const response = await apiService.get<PlanningJob[]>('/api/v2/planning/jobs')
  return response.data
}

export async function createPlanningJob(jobConfig: unknown): Promise<PlanningJob> {
  const response = await apiService.post<PlanningJob>('/api/v2/planning/jobs', jobConfig)
  return response.data
}

export async function deletePlanningJob(jobId: string): Promise<void> {
  await apiService.delete(`/api/v2/planning/jobs/${jobId}`)
}

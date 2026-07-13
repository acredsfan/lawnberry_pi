/**
 * mapsClient.ts — typed client for /api/v2/map/* and /api/v2/planning/*
 *
 * Replaces ApiService methods for maps and planning management.
 */
import apiService from './api'
import type { components } from '@/types/api'

export type Zone = components['schemas']['Zone']
export type MapLocations = components['schemas']['MapLocations']
export interface BoundaryPoint {
  latitude: number
  longitude: number
}

export interface ImportedBoundary {
  source?: string
  source_detail?: string
  confidence?: string
  helper_only?: boolean
  coordinates: BoundaryPoint[]
  warnings?: string[]
  buffer_meters?: number
  status?: string
}

export interface BoundaryVerificationPoint {
  index: number
  reference: BoundaryPoint
  approach: BoundaryPoint
  status: 'pending' | 'starting' | 'traveling' | 'arrived' | 'confirmed' | 'rejected' | 'failed' | 'interrupted'
  mission_id?: string | null
  mission_lifecycle?: string | null
  mission_phase?: 'admitting' | 'heading_validation' | 'heading_bootstrap' | 'waypoint' | string | null
  heading_bootstrap_required?: boolean
  error?: string | null
  evidence?: Record<string, unknown> | null
}

export interface BoundaryVerificationSession {
  session_id?: string
  status: 'idle' | 'active' | 'complete' | 'cancelled'
  points: BoundaryVerificationPoint[]
  target_index: number | null
  active_mission_id?: string | null
  verification_standoff_m?: number
  safe_boundary_buffer_m?: number
  updated_at?: string
}

export interface BoundaryVerificationAcknowledgement {
  operator_confirmed: boolean
  blade_physically_disabled: boolean
  route_clear_confirmed: boolean
  heading_bootstrap_confirmed: boolean
  physical_intervention: string
}

// MapConfiguration and PlanningJob types are not defined in generated schemas,
// so we use unknown and let callers cast or type them at the call site.
export type MapConfiguration = unknown
export type PlanningJob = unknown

export async function getMapZones(): Promise<Zone[]> {
  const response = await apiService.get<Zone[]>('/api/v2/map/zones')
  return response.data
}

export async function bulkReplaceMapZones(zones: Zone[]): Promise<Zone[]> {
  const response = await apiService.post<Zone[]>('/api/v2/map/zones?bulk=true', zones)
  return response.data
}

/** @deprecated Use bulkReplaceMapZones with explicit ?bulk=true intent */
export const postMapZones = bulkReplaceMapZones

export async function getMapZone(id: string): Promise<Zone> {
  const response = await apiService.get<Zone>(`/api/v2/map/zones/${id}`)
  return response.data
}

export async function createMapZone(zone: Zone): Promise<Zone> {
  const response = await apiService.post<Zone>(`/api/v2/map/zones/${zone.id}`, zone)
  return response.data
}

export async function putMapZone(id: string, zone: Zone): Promise<Zone> {
  const response = await apiService.put<Zone>(`/api/v2/map/zones/${id}`, zone)
  return response.data
}

export async function deleteMapZone(id: string): Promise<void> {
  await apiService.delete(`/api/v2/map/zones/${id}`)
}

export async function importParcelBoundary(payload: unknown): Promise<ImportedBoundary> {
  const response = await apiService.post<ImportedBoundary>('/api/v2/parcel/import', payload)
  return response.data
}

export async function getImportedParcelBoundary(): Promise<ImportedBoundary> {
  const response = await apiService.get<ImportedBoundary>('/api/v2/parcel/imported')
  return response.data
}

export async function clearImportedParcelBoundary(): Promise<void> {
  await apiService.post('/api/v2/parcel/clear', {})
}

export async function fetchParcelByPoint(lat: number, lng: number): Promise<ImportedBoundary> {
  const response = await apiService.post<ImportedBoundary>('/api/v2/parcel/fetch-by-point', { lat, lng })
  return response.data
}

export async function fetchParcelByAddress(address: string): Promise<ImportedBoundary> {
  const response = await apiService.post<ImportedBoundary>('/api/v2/parcel/fetch-by-address', { address })
  return response.data
}

export async function generateSafeBoundary(
  coordinates: BoundaryPoint[],
  bufferMeters: number
): Promise<ImportedBoundary> {
  const response = await apiService.post<ImportedBoundary>('/api/v2/boundary/generate-safe', {
    coordinates,
    buffer_meters: bufferMeters,
  })
  return response.data
}

export async function getSafeBoundary(): Promise<ImportedBoundary> {
  const response = await apiService.get<ImportedBoundary>('/api/v2/boundary/safe')
  return response.data
}

export async function startBoundaryVerification(
  coordinates: BoundaryPoint[],
  acknowledgement: BoundaryVerificationAcknowledgement
): Promise<BoundaryVerificationSession> {
  const response = await apiService.post<BoundaryVerificationSession>('/api/v2/boundary-verification/start', {
    coordinates,
    ...acknowledgement,
  })
  return response.data
}

export async function getBoundaryVerificationStatus(): Promise<BoundaryVerificationSession> {
  const response = await apiService.get<BoundaryVerificationSession>('/api/v2/boundary-verification/status')
  return response.data
}

export async function nextBoundaryVerificationPoint(): Promise<BoundaryVerificationSession> {
  const response = await apiService.post<BoundaryVerificationSession>('/api/v2/boundary-verification/next', {})
  return response.data
}

export async function confirmBoundaryVerificationPoint(): Promise<BoundaryVerificationSession> {
  const response = await apiService.post<BoundaryVerificationSession>('/api/v2/boundary-verification/confirm-point', {})
  return response.data
}

export async function rejectBoundaryVerificationPoint(): Promise<BoundaryVerificationSession> {
  const response = await apiService.post<BoundaryVerificationSession>('/api/v2/boundary-verification/reject-point', {})
  return response.data
}

export async function cancelBoundaryVerification(): Promise<BoundaryVerificationSession> {
  const response = await apiService.post<BoundaryVerificationSession>('/api/v2/boundary-verification/cancel', {})
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

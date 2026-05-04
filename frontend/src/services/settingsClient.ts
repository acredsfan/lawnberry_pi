/**
 * settingsClient.ts — typed client for /api/v2/settings/*
 *
 * Replaces ApiService methods for settings management.
 */
import apiService from './api'

// These schemas return untyped dicts from FastAPI; see frontend/src/types/settings.ts for the full shape
export type SettingsResponse = unknown
export type SystemSectionResponse = unknown
export type SecuritySettingsResponse = unknown

export async function getSettings(): Promise<SettingsResponse> {
  const response = await apiService.get<SettingsResponse>('/api/v2/settings')
  return response.data
}

export async function putSettings(settings: Partial<SettingsResponse>): Promise<SettingsResponse> {
  const response = await apiService.put<SettingsResponse>('/api/v2/settings', settings)
  return response.data
}

export async function getSystemSettings(): Promise<SystemSectionResponse> {
  const response = await apiService.get<SystemSectionResponse>('/api/v2/settings/system')
  return response.data
}

export async function putSystemSettings(
  settings: Partial<SystemSectionResponse>
): Promise<SystemSectionResponse> {
  const response = await apiService.put<SystemSectionResponse>(
    '/api/v2/settings/system',
    settings
  )
  return response.data
}

export async function getSecuritySettings(): Promise<SecuritySettingsResponse> {
  const response = await apiService.get<SecuritySettingsResponse>('/api/v2/settings/security')
  return response.data
}

export async function putSecuritySettings(settings: unknown): Promise<SecuritySettingsResponse> {
  const response = await apiService.put<SecuritySettingsResponse>('/api/v2/settings/security', settings)
  return response.data
}

export async function getSafetySettings(): Promise<unknown> {
  const response = await apiService.get('/api/v2/settings/safety')
  return response.data
}

export async function putSafetySettings(settings: unknown): Promise<unknown> {
  const response = await apiService.put('/api/v2/settings/safety', settings)
  return response.data
}

export async function getMapsSettings(): Promise<unknown> {
  const response = await apiService.get('/api/v2/settings/maps')
  return response.data
}

export async function putMapsSettings(settings: unknown): Promise<unknown> {
  const response = await apiService.put('/api/v2/settings/maps', settings)
  return response.data
}

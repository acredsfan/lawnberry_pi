/**
 * telemetryClient.ts — typed client for /api/v2/telemetry/* and /api/v2/dashboard/*
 *
 * Replaces ApiService.getTelemetryStream(), ApiService.exportTelemetryDiagnostic(),
 * and ApiService.pingTelemetry() defined directly on the class in api.ts.
 */
import apiService from './api'
import type { components } from '@/types/api'

export type TelemetryPingRequest = components['schemas']['TelemetryPingRequest']
export type MowerStatus = components['schemas']['MowerStatus']

// DashboardTelemetry and TelemetryPingResponse are not defined in generated schemas,
// so we use unknown and let callers cast or type them at the call site.
export type DashboardTelemetry = unknown
export type TelemetryPingResponse = unknown

export interface TelemetryStreamParams {
  limit?: number
  since?: string | null
}

export interface TelemetryExportParams {
  component?: string | null
  start?: string | null
  end?: string | null
  format?: string
}

export async function getTelemetryStream(params?: TelemetryStreamParams) {
  const query = new URLSearchParams()
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        query.append(key, String(value))
      }
    }
  }
  const qs = query.toString()
  const response = await apiService.get(
    `/api/v2/telemetry/stream${qs ? `?${qs}` : ''}`
  )
  return response.data
}

export async function exportTelemetryDiagnostic(
  params?: TelemetryExportParams
): Promise<Blob> {
  const query = new URLSearchParams()
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        query.append(key, String(value))
      }
    }
  }
  const qs = query.toString()
  const response = await apiService.get(
    `/api/v2/telemetry/export${qs ? `?${qs}` : ''}`,
    { responseType: 'blob' }
  )
  return response.data as Blob
}

export async function pingTelemetry(
  request: TelemetryPingRequest
): Promise<TelemetryPingResponse> {
  const response = await apiService.post<TelemetryPingResponse>(
    '/api/v2/telemetry/ping',
    request
  )
  return response.data
}

export async function getDashboardTelemetry(): Promise<DashboardTelemetry> {
  const response = await apiService.get<DashboardTelemetry>(
    '/api/v2/dashboard/telemetry'
  )
  return response.data
}

export async function getDashboardStatus(): Promise<MowerStatus> {
  const response = await apiService.get<MowerStatus>(
    '/api/v2/dashboard/status'
  )
  return response.data
}

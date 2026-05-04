/**
 * controlClient.ts — typed client for /api/v2/control/* and /api/v2/hardware/robohat
 *
 * Replaces the hand-written sendControlCommand(), getRoboHATStatus(),
 * getControlStatus(), and clearEmergencyStop() functions in api.ts.
 */
import apiService from './api'
import type { components } from '@/types/api'

export type ControlResponseV2 = components['schemas']['ControlResponseV2']

// RoboHATStatus and ControlStatus schemas not yet available in OpenAPI spec;
// use untyped responses for now
export type RoboHATStatus = unknown
export type ControlStatus = unknown

export interface DrivePayload {
  throttle: number   // -1.0 .. 1.0
  turn: number       // -1.0 .. 1.0
  duration_ms?: number
}

export interface BladePayload {
  active: boolean
}

export interface EmergencyPayload {
  reason?: string
}

export interface EmergencyClearPayload {
  confirmation: boolean
  reason?: string
}

export async function sendDrive(payload: DrivePayload): Promise<ControlResponseV2> {
  const response = await apiService.post<ControlResponseV2>(
    '/api/v2/control/drive',
    payload
  )
  return response.data
}

export async function sendBlade(payload: BladePayload): Promise<{ ok: boolean }> {
  const response = await apiService.post<{ ok: boolean }>(
    '/api/v2/control/blade',
    payload
  )
  return response.data
}

export async function sendEmergencyStop(
  payload: EmergencyPayload = {}
): Promise<ControlResponseV2> {
  const response = await apiService.post<ControlResponseV2>(
    '/api/v2/control/emergency',
    payload
  )
  return response.data
}

export async function clearEmergencyStop(
  payload: EmergencyClearPayload
): Promise<{ ok: boolean }> {
  const response = await apiService.post<{ ok: boolean }>(
    '/api/v2/control/emergency_clear',
    payload
  )
  return response.data
}

export async function getControlStatus(): Promise<ControlStatus> {
  const response = await apiService.get<ControlStatus>('/api/v2/control/status')
  return response.data
}

export async function getRoboHATStatus(): Promise<RoboHATStatus> {
  const response = await apiService.get<RoboHATStatus>('/api/v2/hardware/robohat')
  return response.data
}

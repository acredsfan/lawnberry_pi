// Control API methods
export async function sendControlCommand(command: string, payload: any = {}) {
  // Map command to endpoint
  let url = ''
  switch (command) {
    case 'drive':
      url = '/api/v2/control/drive'
      break
    case 'blade':
      url = '/api/v2/control/blade'
      break
    case 'emergency':
      url = '/api/v2/control/emergency'
      break
    default:
      throw new Error(`Unknown control command: ${command}`)
  }
  const response = await apiService.post(url, payload)
  return response.data
}

export async function getRoboHATStatus() {
  const response = await apiService.get('/api/v2/hardware/robohat')
  return response.data
}

// Map API methods
export async function getMapConfiguration(configId: string = 'default') {
  const response = await apiService.get(`/api/v2/map/configuration?config_id=${configId}`)
  return response.data
}

export async function saveMapConfiguration(configId: string, config: any) {
  const response = await apiService.put(`/api/v2/map/configuration?config_id=${configId}`, config)
  return response.data
}

export async function triggerMapProviderFallback() {
  const response = await apiService.post('/api/v2/map/provider-fallback')
  return response.data
}
import axios from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'

const CLIENT_ID_STORAGE_KEY = 'lawnberry-client-id'
const CLIENT_ID_GLOBAL_KEY = '__LAWN_CLIENT_ID__'

function generateClientId(): string {
  const randomId = `web-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`

  if (typeof window !== 'undefined') {
    try {
      const existing = window.localStorage?.getItem(CLIENT_ID_STORAGE_KEY)
      if (existing) {
        return existing
      }
      window.localStorage?.setItem(CLIENT_ID_STORAGE_KEY, randomId)
      return randomId
    } catch (error) {
      /* localStorage unavailable, fall through */
    }
  }

  const globalScope = globalThis as Record<string, unknown>
  const existingGlobal = globalScope[CLIENT_ID_GLOBAL_KEY]
  if (typeof existingGlobal === 'string' && existingGlobal.length > 0) {
    return existingGlobal
  }
  globalScope[CLIENT_ID_GLOBAL_KEY] = randomId
  return randomId
}

class ApiService {
  private client: AxiosInstance

  constructor() {
    // Compute default base URL from current origin to use frontend proxy (/api and /api/v2)
    const defaultBase = ''
    const clientId = generateClientId()
    this.client = axios.create({
      baseURL: defaultBase,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
        'X-Client-Id': clientId
      }
    })

    // Request interceptor to add auth token
    this.client.interceptors.request.use(
      (config) => {
        const authStore = useAuthStore()
        if (authStore.token) {
          config.headers.Authorization = `Bearer ${authStore.token}`
        }
        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          const authStore = useAuthStore()
          authStore.logout()
        }
        return Promise.reject(error)
      }
    )
  }

  async get<T = any>(url: string): Promise<AxiosResponse<T>> {
    return this.client.get<T>(url)
  }

  async post<T = any>(url: string, data?: any): Promise<AxiosResponse<T>> {
    return this.client.post<T>(url, data)
  }

  async put<T = any>(url: string, data?: any): Promise<AxiosResponse<T>> {
    return this.client.put<T>(url, data)
  }

  async delete<T = any>(url: string): Promise<AxiosResponse<T>> {
    return this.client.delete<T>(url)
  }

  async patch<T = any>(url: string, data?: any): Promise<AxiosResponse<T>> {
    return this.client.patch<T>(url, data)
  }

  // Telemetry API methods
  async getTelemetryStream(params?: {
    page?: number
    per_page?: number
    component_id?: string
    start_time?: string
    end_time?: string
  }) {
    const query = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          query.append(key, String(value))
        }
      })
    }
    const queryString = query.toString()
    return this.get(`/api/v2/telemetry/stream${queryString ? `?${queryString}` : ''}`)
  }

  async exportTelemetryDiagnostic(params?: {
    component_id?: string
    start_time?: string
    end_time?: string
  }) {
    const query = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          query.append(key, String(value))
        }
      })
    }
    const queryString = query.toString()
    return this.client.get(`/api/v2/telemetry/export${queryString ? `?${queryString}` : ''}`, {
      responseType: 'blob'
    })
  }

  async pingTelemetry(data: {
    component_id: string
    sample_count?: number
  }) {
    return this.post('/api/v2/telemetry/ping', data)
  }
}

// Singleton instance
const apiService = new ApiService()

// Composable for use in Vue components
export function useApiService() {
  return apiService
}

export default apiService
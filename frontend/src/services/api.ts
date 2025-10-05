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

class ApiService {
  private client: AxiosInstance

  constructor() {
    // Compute default base URL from current origin to use frontend proxy (/api and /api/v2)
    const defaultBase = ''
    this.client = axios.create({
      baseURL: defaultBase,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json'
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
import axios from 'axios'
import type { AxiosInstance } from 'axios'
import type { AuthResponse, RefreshResponse, LoginCredentials, User } from '@/types/auth'

// Create axios instance with base configuration
const apiClient: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token expired, try to refresh
      try {
        const response = await authApi.refresh()
        localStorage.setItem('auth_token', response.access_token)
        
        // Retry original request
        const originalRequest = error.config
        originalRequest.headers.Authorization = `Bearer ${response.access_token}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        // Refresh failed, redirect to login
        localStorage.removeItem('auth_token')
        window.location.href = '/login'
        throw refreshError
      }
    }
    throw error
  }
)

// Auth API endpoints
export const authApi = {
  login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
    const response = await apiClient.post('/auth/login', credentials)
    return response.data
  },

  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout')
  },

  refresh: async (): Promise<RefreshResponse> => {
    const response = await apiClient.post('/auth/refresh')
    return response.data
  },

  getProfile: async (): Promise<User> => {
    const response = await apiClient.get('/auth/profile')
    return response.data
  },
}

// System API endpoints  
export const systemApi = {
  getStatus: async () => {
    const response = await apiClient.get('/dashboard/status')
    return response.data
  },

  getHealth: async () => {
    const response = await apiClient.get('/system/health')
    return response.data
  },

  shutdown: async () => {
    const response = await apiClient.post('/system/shutdown')
    return response.data
  },

  restart: async () => {
    const response = await apiClient.post('/system/restart')
    return response.data
  },
}

// Control API endpoints
export const controlApi = {
  start: async () => {
    const response = await apiClient.post('/control/start')
    return response.data
  },

  stop: async () => {
    const response = await apiClient.post('/control/stop')
    return response.data
  },

  pause: async () => {
    const response = await apiClient.post('/control/pause')
    return response.data
  },

  resume: async () => {
    const response = await apiClient.post('/control/resume')
    return response.data
  },

  emergencyStop: async () => {
    const response = await apiClient.post('/control/emergency-stop')
    return response.data
  },

  getStatus: async () => {
    const response = await apiClient.get('/control/status')
    return response.data
  },
}

// Maps API endpoints
export const mapsApi = {
  getMaps: async () => {
    const response = await apiClient.get('/maps')
    return response.data
  },

  createMap: async (mapData: any) => {
    const response = await apiClient.post('/maps', mapData)
    return response.data
  },

  updateMap: async (mapId: string, mapData: any) => {
    const response = await apiClient.put(`/maps/${mapId}`, mapData)
    return response.data
  },

  deleteMap: async (mapId: string) => {
    const response = await apiClient.delete(`/maps/${mapId}`)
    return response.data
  },

  startMapping: async () => {
    const response = await apiClient.post('/maps/start-mapping')
    return response.data
  },

  stopMapping: async () => {
    const response = await apiClient.post('/maps/stop-mapping')
    return response.data
  },
}

// Planning API endpoints
export const planningApi = {
  getPlans: async () => {
    const response = await apiClient.get('/planning')
    return response.data
  },

  createPlan: async (planData: any) => {
    const response = await apiClient.post('/planning', planData)
    return response.data
  },

  updatePlan: async (planId: string, planData: any) => {
    const response = await apiClient.put(`/planning/${planId}`, planData)
    return response.data
  },

  deletePlan: async (planId: string) => {
    const response = await apiClient.delete(`/planning/${planId}`)
    return response.data
  },

  executePlan: async (planId: string) => {
    const response = await apiClient.post(`/planning/${planId}/execute`)
    return response.data
  },
}

// Settings API endpoints
export const settingsApi = {
  getSettings: async () => {
    const response = await apiClient.get('/settings')
    return response.data
  },

  updateSettings: async (settings: any) => {
    const response = await apiClient.put('/settings', settings)
    return response.data
  },

  resetToDefaults: async () => {
    const response = await apiClient.post('/settings/reset')
    return response.data
  },
}

// Telemetry API endpoints
export const telemetryApi = {
  getCurrent: async () => {
    const response = await apiClient.get('/dashboard/telemetry')
    return response.data
  },

  getHistory: async (startTime?: string, endTime?: string) => {
    const params = new URLSearchParams()
    if (startTime) params.append('start_time', startTime)
    if (endTime) params.append('end_time', endTime)
    
    const response = await apiClient.get(`/telemetry/history?${params}`)
    return response.data
  },

  export: async (format: 'json' | 'csv' = 'json', startTime?: string, endTime?: string) => {
    const params = new URLSearchParams()
    params.append('format', format)
    if (startTime) params.append('start_time', startTime)
    if (endTime) params.append('end_time', endTime)
    
    const response = await apiClient.get(`/telemetry/export?${params}`, {
      responseType: 'blob'
    })
    return response.data
  },
}

// AI API endpoints
export const aiApi = {
  getStatus: async () => {
    const response = await apiClient.get('/ai/status')
    return response.data
  },

  startTraining: async (trainingConfig: any) => {
    const response = await apiClient.post('/ai/training/start', trainingConfig)
    return response.data
  },

  stopTraining: async () => {
    const response = await apiClient.post('/ai/training/stop')
    return response.data
  },

  getTrainingStatus: async () => {
    const response = await apiClient.get('/ai/training/status')
    return response.data
  },

  uploadTrainingData: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await apiClient.post('/ai/training/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  },
}

// Weather API endpoints
export const weatherApi = {
  getCurrent: async (params?: { lat?: number; lon?: number }) => {
    const query = new URLSearchParams()
    if (params?.lat !== undefined) query.append('lat', String(params.lat))
    if (params?.lon !== undefined) query.append('lon', String(params.lon))
    const path = query.toString() ? `/weather/current?${query}` : '/weather/current'
    const response = await apiClient.get(path)
    return response.data as {
      temperature_c: number
      humidity_percent: number
      wind_speed_mps: number
      condition: string
      source: string
      ts: string
    }
  },

  getPlanningAdvice: async () => {
    const response = await apiClient.get('/weather/planning-advice')
    return response.data as {
      advice: 'proceed' | 'avoid' | 'caution'
      reason: string
      next_review_at: string
    }
  },
}

export default apiClient
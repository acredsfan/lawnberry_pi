import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
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

  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> {
    return this.client.get<T>(url, config)
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
}

// Singleton instance
const apiService = new ApiService()

// Composable for use in Vue components
export function useApiService() {
  return apiService
}

export default apiService
import axios, { AxiosInstance, AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'

class ApiService {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
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
}

// Singleton instance
const apiService = new ApiService()

// Composable for use in Vue components
export function useApiService() {
  return apiService
}

export default apiService
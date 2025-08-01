import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';

// API Base URL configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Create axios instance with default configuration
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for adding auth tokens or other headers
apiClient.interceptors.request.use(
  (config: AxiosRequestConfig) => {
    // Add authentication token if available
    const token = localStorage.getItem('auth_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for handling common errors
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error) => {
    // Handle common HTTP errors
    if (error.response?.status === 401) {
      // Handle unauthorized access
      localStorage.removeItem('auth_token');
      // Optionally redirect to login
    } else if (error.response?.status === 500) {
      console.error('Server error:', error.response.data);
    }
    return Promise.reject(error);
  }
);

// API client methods
export const api = {
  // Generic methods
  get: <T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> =>
    apiClient.get<T>(url, config),
  
  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> =>
    apiClient.post<T>(url, data, config),
  
  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> =>
    apiClient.put<T>(url, data, config),
  
  patch: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> =>
    apiClient.patch<T>(url, data, config),
  
  delete: <T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> =>
    apiClient.delete<T>(url, config),

  // RC Control specific methods
  rc: {
    getStatus: () => api.get('/api/v1/rc/status'),
    getChannels: () => api.get('/api/v1/rc/channels'),
    updateChannel: (channel: number, config: any) => 
      api.put(`/api/v1/rc/channels/${channel}`, config),
    enableRC: (enabled: boolean) => 
      api.post('/api/v1/rc/enable', { enabled }),
    setMode: (mode: string) => 
      api.post('/api/v1/rc/mode', { mode }),
    sendCommand: (command: string, parameters?: any) =>
      api.post('/api/v1/rc/command', { command, parameters }),
  },

  // Mower control methods
  mower: {
    getStatus: () => api.get('/api/v1/mower/status'),
    start: () => api.post('/api/v1/mower/start'),
    stop: () => api.post('/api/v1/mower/stop'),
    pause: () => api.post('/api/v1/mower/pause'),
    emergencyStop: () => api.post('/api/v1/mower/emergency-stop'),
    setPattern: (patternId: string) => 
      api.post('/api/v1/mower/pattern', { pattern: patternId }),
  },

  // Navigation methods
  navigation: {
    getPosition: () => api.get('/api/v1/navigation/position'),
    getBoundaries: () => api.get('/api/v1/navigation/boundaries'),
    getNoGoZones: () => api.get('/api/v1/navigation/no-go-zones'),
    updateBoundary: (id: string, boundary: any) =>
      api.put(`/api/v1/navigation/boundaries/${id}`, boundary),
  },

  // System methods
  system: {
    getHealth: () => api.get('/api/v1/system/health'),
    getSettings: () => api.get('/api/v1/system/settings'),
    updateSettings: (settings: any) => 
      api.put('/api/v1/system/settings', settings),
  },
};

// Export both the configured client and the API methods
export { apiClient };
export default api;

export interface SensorData {
  timestamp: number
  value: number | string | boolean
  unit?: string
  status: 'online' | 'offline' | 'error'
}

export interface MowerStatus {
  state: 'idle' | 'mowing' | 'charging' | 'returning' | 'error' | 'emergency'
  position: {
    lat: number
    lng: number
    heading: number
    accuracy: number
  }
  battery: {
    level: number
    voltage: number
    current: number
    power?: number
    charging: boolean
    timeRemaining?: number
  }
  solar?: {
    voltage: number
    current: number
    power: number
  }
  sensors: {
    imu: {
      orientation: { x: number; y: number; z: number }
      acceleration: { x: number; y: number; z: number }
      gyroscope: { x: number; y: number; z: number }
      temperature: number
    }
    tof: {
      left: number
      right: number
    }
    environmental: {
      temperature: number
      humidity: number
      pressure: number
    }
    power: {
      battery_voltage: number
      battery_current: number
      battery_power: number
      solar_voltage: number
      solar_current: number
      solar_power: number
    }
  }
  coverage: {
    totalArea: number
    coveredArea: number
    percentage: number
  }
  lastUpdate: number
  location_source: 'gps' | 'rtk' | 'visual' | 'imu' | 'manual' | 'config'
  connected: boolean
}

export interface WeatherData {
  current: {
    temperature: number
    humidity: number
    windSpeed: number
    windDirection: number
    precipitation: number
    condition: string
    icon: string
  }
  forecast: Array<{
    date: string
    temperature: { min: number; max: number }
    condition: string
    icon: string
    precipitation: number
  }>
  alerts: Array<{
    id: string
    title: string
    description: string
    severity: 'minor' | 'moderate' | 'severe' | 'extreme'
    start: number
    end: number
  }>
}

export type MowingPattern = {
  id: string
  name: string
  description: string
} & (
  | {
      type: 'parallel'
      parameters: {
        spacing?: number
        angle?: number
        overlap?: number
      }
    }
  | {
      type: 'checkerboard'
      parameters: {
        spacing?: number
        overlap?: number
      }
    }
  | {
      type: 'spiral'
      parameters: {
        spacing?: number
        centerPoint?: { lat: number; lng: number }
      }
    }
  | {
      type: 'waves'
      parameters: {
        spacing?: number
        amplitude: number
        wavelength: number
        angle?: number
      }
    }
  | {
      type: 'crosshatch'
      parameters: {
        spacing?: number
        first_angle: number
        second_angle: number
        overlap?: number
        base_angle?: number
      }
    }
)

export interface YardBoundary {
  id: string
  name: string
  coordinates: Array<{ lat: number; lng: number }>
  type: 'boundary' | 'no-go' | 'home'
}

export interface Boundary {
  id: string
  name: string
  coordinates: Array<{ lat: number; lng: number }>
  type: 'boundary'
}

export interface NoGoZone {
  id: string
  name: string
  coordinates: Array<{ lat: number; lng: number }>
  type: 'no-go'
}

export interface HomeLocation {
  id: string
  name: string
  coordinates: Array<{ lat: number; lng: number }>
  type: 'home'
}

export interface Schedule {
  id: string
  name: string
  enabled: boolean
  days: Array<'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday'>
  startTime: string
  duration: number
  pattern: string
  conditions: {
    minBattery: number
    maxWindSpeed: number
    noRain: boolean
  }
}

export interface SystemSettings {
  units: {
    temperature: 'celsius' | 'fahrenheit'
    distance: 'metric' | 'imperial'
    speed: 'ms' | 'kmh' | 'mph'
  }
  safety: {
    emergencyStopDistance: number
    maxSlope: number
    obstacleDetectionSensitivity: number
    responseTime: number
  }
  operation: {
    defaultSpeed: number
    batteryThresholds: {
      low: number
      critical: number
      return: number
    }
  }
  display: {
    theme: 'light' | 'dark' | 'auto'
    refreshRate: number
    showAdvanced: boolean
  reducedMotion?: boolean
  lowPowerMode?: boolean
  }
}

export interface TrainingImage {
  id: string
  filename: string
  timestamp: number
  labels: Array<{
    id: string
    name: string
    bbox: { x: number; y: number; width: number; height: number }
    confidence?: number
  }>
  processed: boolean
}

export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  timestamp: number
}

export interface WebSocketMessage {
  type: string
  topic: string
  payload: any
  timestamp: number
}

export interface NavigationState {
  currentPath: Array<{ lat: number; lng: number }>
  plannedPath: Array<{ lat: number; lng: number }>
  obstacles: Array<{
    id: string
    position: { lat: number; lng: number }
    size: { width: number; height: number }
    type: string
    confidence: number
  }>
  coverage: Array<{ lat: number; lng: number; covered: boolean }>
}

export type MapProvider = 'google' | 'openstreetmap'

export type MapUsageLevel = 'high' | 'medium' | 'low'

export interface MapConfig {
  provider: MapProvider
  usageLevel: MapUsageLevel
  apiKey?: string
  defaultCenter: { lat: number; lng: number }
  defaultZoom: number
  enableCaching: boolean
  offlineMode: boolean
}

export interface MapError {
  type: 'api_key_invalid' | 'quota_exceeded' | 'network_error' | 'billing_error' | 'generic'
  message: string
  provider: MapProvider
  canFallback: boolean
}

export interface MapState {
  isLoading: boolean
  error: MapError | null
  currentProvider: MapProvider
  isOffline: boolean
  cacheStatus: 'empty' | 'partial' | 'full'
}

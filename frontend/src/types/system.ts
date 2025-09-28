export type SystemStatus = 'active' | 'warning' | 'error' | 'unknown' | 'maintenance'
export type ConnectionStatus = 'connected' | 'disconnected' | 'connecting' | 'error'

export interface TelemetryData {
  timestamp: string
  sensors: {
    gps?: any
    imu?: any
    tof?: any
    environmental?: any
    power?: any
    health: boolean
  }
  motors: {
    left?: any
    right?: any
    blade?: any
    health: boolean
  }
  navigation: {
    position?: any
    target?: any
    status?: string
    health: boolean
  }
  system: {
    cpu_usage: number
    memory_usage: number
    temperature: number
    uptime: number
  }
}
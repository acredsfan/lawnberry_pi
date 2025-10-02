/**
 * Telemetry types for LawnBerry Pi v2
 * Hardware telemetry data structures for frontend consumption
 */

export interface TelemetryLatencyBadge {
  latency_ms: number
  status: 'healthy' | 'warning' | 'critical'
  target_ms: number
  device: 'pi5' | 'pi4'
}

export interface RTKStatus {
  fix_type: 'no_fix' | 'gps_fix' | 'dgps_fix' | 'rtk_float' | 'rtk_fixed'
  status_message: string
  satellites: number
  hdop: number
  requires_remediation: boolean
  remediation_link?: string
}

export interface IMUOrientation {
  roll_deg: number
  pitch_deg: number
  yaw_deg: number
  quaternion_w: number
  quaternion_x: number
  quaternion_y: number
  quaternion_z: number
  calibration_sys: number
  calibration_gyro: number
  calibration_accel: number
  calibration_mag: number
  health_status: 'healthy' | 'warning' | 'fault'
  remediation_link?: string
}

export interface PowerMetrics {
  battery: {
    voltage: number
    current: number
    power: number
    soc_percent: number | null
    health: 'healthy' | 'warning' | 'fault'
  }
  solar: {
    voltage: number
    current: number
    power: number
  }
  timestamp: string
}

export interface HardwareTelemetryStream {
  timestamp: string
  component_id: string
  value: any
  status: 'healthy' | 'warning' | 'fault'
  latency_ms: number
  gps_data?: {
    latitude: number
    longitude: number
    altitude_m: number
    speed_mps: number
    heading_deg: number
    hdop: number
    satellites: number
    fix_type: string
    rtk_status_message: string | null
  }
  imu_data?: {
    roll_deg: number
    pitch_deg: number
    yaw_deg: number
    quaternion_w: number
    quaternion_x: number
    quaternion_y: number
    quaternion_z: number
    accel_x: number
    accel_y: number
    accel_z: number
    gyro_x: number
    gyro_y: number
    gyro_z: number
    calibration_sys: number
    calibration_gyro: number
    calibration_accel: number
    calibration_mag: number
  }
  power_data?: {
    battery_voltage: number
    battery_current: number
    battery_power: number
    solar_voltage: number
    solar_current: number
    solar_power: number
    battery_soc_percent: number | null
    battery_health: 'healthy' | 'warning' | 'fault'
  }
  tof_data?: {
    distance_mm: number
    range_status: string
    signal_rate: number
  }
  metadata?: Record<string, any>
  verification_artifact_id?: string | null
}

export interface TelemetryStreamResponse {
  streams: HardwareTelemetryStream[]
  count: number
  latency_stats: {
    avg_latency_ms: number
    max_latency_ms: number
    min_latency_ms: number
    stream_count: number
  }
  rtk_status?: RTKStatus
  imu_orientation?: IMUOrientation
  timestamp: string
}

export interface TelemetryExportData {
  export_timestamp: string
  filters: {
    component_id: string | null
    start_time: string | null
    end_time: string | null
  }
  statistics: {
    avg_latency_ms: number
    max_latency_ms: number
    min_latency_ms: number
    stream_count: number
  }
  stream_count: number
  streams: HardwareTelemetryStream[]
}

export interface TelemetryPingResponse {
  component_id: string
  sample_count: number
  latency_ms: number
  avg_latency_ms: number
  min_latency_ms: number
  max_latency_ms: number
  p95_latency_ms: number
  meets_target: boolean
  target_ms: number
  device: 'pi5' | 'pi4'
  remediation?: {
    message: string
    doc_link: string
  }
}

export interface DashboardTelemetry {
  timestamp: string
  latency_badge: TelemetryLatencyBadge
  rtk_status: RTKStatus | null
  imu_orientation: IMUOrientation | null
  power_metrics: PowerMetrics
  gps: {
    latitude: number | null
    longitude: number | null
    altitude: number | null
    accuracy: number | null
    satellites: number
    fix_type: string
  }
  motors: {
    drive_left_pwm: number
    drive_right_pwm: number
    blade_pwm: number
    status: 'idle' | 'running' | 'error'
  }
  safety: {
    state: 'safe' | 'warning' | 'emergency'
    messages: string[]
  }
}

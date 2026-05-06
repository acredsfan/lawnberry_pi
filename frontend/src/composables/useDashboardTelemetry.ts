import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/services/websocket'

export function useDashboardTelemetry() {
  const ws = useWebSocket('telemetry')

  const batteryData = ref<Record<string, unknown> | null>(null)
  const positionData = ref<Record<string, unknown> | null>(null)
  const orientationData = ref<Record<string, unknown> | null>(null)
  const environmentalData = ref<Record<string, unknown> | null>(null)
  const systemData = ref<Record<string, unknown> | null>(null)
  const tofData = ref<Record<string, unknown> | null>(null)
  const imuData = ref<Record<string, unknown> | null>(null)
  const safetyData = ref<Record<string, unknown> | null>(null)
  const eventLog = ref<Record<string, unknown>[]>([])

  // telemetry.power → { power: {battery_voltage, battery_current, battery_power, solar_*…}, battery: {percentage, voltage} }
  function handlePower(data: Record<string, unknown>) {
    const battery = data.battery as Record<string, unknown> | undefined
    const power = data.power as Record<string, unknown> | undefined
    batteryData.value = {
      percentage: battery?.percentage,
      voltage: battery?.voltage ?? power?.battery_voltage,
      current: power?.battery_current,
      power: power?.battery_power,
      charging: typeof power?.battery_current === 'number' ? (power!.battery_current as number) < -0.05 : false,
    }
  }

  // telemetry.navigation → { position: {latitude, longitude, accuracy, satellites, speed, heading, rtk_status, hdop}, velocity, nav_heading }
  function handleNavigation(data: Record<string, unknown>) {
    const pos = data.position as Record<string, unknown> | undefined
    const vel = data.velocity as Record<string, unknown> | undefined
    const linear = vel?.linear as Record<string, unknown> | undefined
    positionData.value = {
      latitude: pos?.latitude,
      longitude: pos?.longitude,
      accuracy: pos?.accuracy,
      satellites: pos?.satellites,
      hdop: pos?.hdop,
      rtk_status: pos?.rtk_status,
    }
    // Speed and heading live here; merge with any existing imu orientation fields
    orientationData.value = {
      ...(orientationData.value ?? {}),
      speed: linear?.x ?? pos?.speed,
      heading: data.nav_heading ?? pos?.heading,
    }
  }

  // telemetry.sensors → { imu: {yaw, pitch, roll, gyro_z, calibration, calibration_status} }
  function handleSensors(data: Record<string, unknown>) {
    const imu = data.imu as Record<string, unknown> | undefined
    imuData.value = imu ?? null
    // Merge yaw/pitch/roll into orientationData alongside speed/heading from navigation
    orientationData.value = {
      ...(orientationData.value ?? {}),
      yaw: imu?.yaw,
      pitch: imu?.pitch,
      roll: imu?.roll,
    }
  }

  // telemetry.environmental → { environmental: {temperature_c, humidity_percent, pressure_hpa, altitude_m} }
  function handleEnvironmental(data: Record<string, unknown>) {
    const env = data.environmental as Record<string, unknown> | undefined
    environmentalData.value = {
      temperature: env?.temperature_c,
      humidity: env?.humidity_percent,
      pressure: env?.pressure_hpa,
      altitude: env?.altitude_m,
    }
  }

  // telemetry.system → { safety_state, uptime_seconds, source }
  function handleSystem(data: Record<string, unknown>) {
    systemData.value = {
      status: data.safety_state,
      safety_state: data.safety_state,
      mode: data.mode ?? data.motor_status,
      uptime_seconds: data.uptime_seconds,
    }
  }

  function handleTof(data: Record<string, unknown>) { tofData.value = data }
  function handleSafety(data: Record<string, unknown>) { safetyData.value = data }
  function handleEvent(data: Record<string, unknown>) {
    eventLog.value = [data, ...eventLog.value].slice(0, 100)
  }

  const subscriptions: Array<[string, (d: Record<string, unknown>) => void]> = [
    ['telemetry.power', handlePower],
    ['telemetry.navigation', handleNavigation],
    ['telemetry.sensors', handleSensors],
    ['telemetry.environmental', handleEnvironmental],
    ['telemetry.system', handleSystem],
    ['telemetry.tof', handleTof],
    ['telemetry.safety', handleSafety],
    ['telemetry.event', handleEvent],
  ]

  onMounted(async () => {
    try {
      await ws.connect()
      ws.setCadence(5)
      subscriptions.forEach(([topic, handler]) => ws.subscribe(topic, handler))
    } catch (error) {
      console.warn('useDashboardTelemetry: WS connect failed', error)
    }
  })

  onUnmounted(() => {
    subscriptions.forEach(([topic, handler]) => ws.unsubscribe(topic, handler))
  })

  return {
    batteryData, positionData, orientationData, environmentalData,
    systemData, tofData, imuData, safetyData, eventLog,
  }
}

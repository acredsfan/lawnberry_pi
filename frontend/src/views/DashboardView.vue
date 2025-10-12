<template>
  <div class="dashboard retro-dashboard">
    <!-- Retro Header -->
    <div class="retro-header">
      <div class="header-glow" />
      <h1 class="retro-title">SYSTEM DASHBOARD</h1>
      <p class="retro-subtitle">REAL-TIME MONITORING & CONTROL INTERFACE</p>
      <div class="data-stream">{{ dataStreamText }}</div>
    </div>

    <div class="dashboard-grid">
      <!-- System Status -->
      <div class="retro-card status-card">
        <div class="card-header">
          <h3>◢ SYSTEM STATUS ◣</h3>
          <div class="status-indicator" :class="systemStatusClass" />
        </div>
        <div class="card-content">
          <div class="status-row">
            <span class="status-label">UPTIME:</span>
            <span class="status-value uptime">{{ uptime }}</span>
          </div>
          <div class="status-row">
            <span class="status-label">CONNECTION:</span>
            <span class="status-value" :class="connectionStatusClass">{{ connectionStatus }}</span>
          </div>
          <div class="status-row">
            <span class="status-label">OVERALL:</span>
            <span class="status-value" :class="systemStatusClass">{{ systemStatus }}</span>
          </div>
        </div>
      </div>

      <!-- Quick Controls -->
      <div class="retro-card control-card">
        <div class="card-header">
          <h3>◢ QUICK CONTROLS ◣</h3>
          <div class="power-indicator" :class="{ active: currentMode !== 'IDLE' }" />
        </div>
        <div class="card-content">
          <div class="control-grid">
            <button class="retro-btn start-btn" :disabled="isLoading" @click="startSystem">
              <span class="btn-icon">▶</span>
              START
            </button>
            <button class="retro-btn pause-btn" :disabled="isLoading" @click="pauseSystem">
              <span class="btn-icon">⏸</span>
              PAUSE
            </button>
            <button class="retro-btn stop-btn" :disabled="isLoading" @click="stopSystem">
              <span class="btn-icon">⏹</span>
              STOP
            </button>
            <button class="retro-btn emergency-btn" :disabled="isLoading" @click="emergencyStop">
              <span class="btn-icon">⚠</span>
              E-STOP
            </button>
          </div>
          <div class="mode-display">
            MODE: <span class="mode-value">{{ currentMode }}</span>
          </div>
        </div>
      </div>

      <!-- Current Activity -->
      <div class="retro-card activity-card">
        <div class="card-header">
          <h3>◢ CURRENT ACTIVITY ◣</h3>
          <div class="activity-pulse" />
        </div>
        <div class="card-content">
          <div class="progress-container">
            <div class="progress-label">{{ progress }}% COMPLETE</div>
            <div class="retro-progress">
              <div class="progress-bar" :style="{ width: `${progress}%` }" />
              <div class="progress-grid" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Live Telemetry Grid -->
    <div class="telemetry-grid">
      <!-- GPS Position -->
      <div class="retro-card telemetry-card">
        <div class="card-header">
          <h4>GPS POSITION</h4>
          <div class="gps-icon">📡</div>
        </div>
        <div class="card-content">
          <div class="metric-value gps-value">
            <template v-if="hasGpsFix">
              <span class="coord">
                <span class="coord-label">LAT</span>
                <span class="coord-value">{{ gpsLatitude }}</span>
              </span>
              <span class="coord">
                <span class="coord-label">LON</span>
                <span class="coord-value">{{ gpsLongitude }}</span>
              </span>
            </template>
            <span v-else class="coord no-fix">NO SIGNAL</span>
          </div>
          <div class="metric-status" :class="gpsStatusClass">{{ gpsStatus }}</div>
          <div class="gps-metrics" v-if="hasGpsFix">
            <div class="metric-line">
              ACCURACY: <span>{{ gpsAccuracyDisplay }} {{ gpsAccuracyUnit }}</span>
            </div>
            <div class="metric-line">
              HDOP: <span>{{ gpsHdopDisplay }}</span>
            </div>
            <div class="metric-line">
              SATS: <span>{{ gpsSatellitesDisplay }}</span>
            </div>
            <div class="metric-line" v-if="gpsRtkStatus">
              RTK: <span>{{ gpsRtkStatus }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Battery Level -->
      <div class="retro-card telemetry-card battery-card">
        <div class="card-header">
          <h4>POWER LEVEL</h4>
          <div class="battery-icon" :class="batteryIconClass">🔋</div>
        </div>
        <div class="card-content">
          <div class="metric-value">{{ batteryLevelDisplay }}%</div>
          <div class="battery-bar">
            <div class="battery-fill" :style="{ width: `${batteryLevel}%` }" :class="batteryBarClass" />
            <div class="battery-segments" />
          </div>
          <div class="metric-status">{{ batteryVoltageDisplay }}V</div>
        </div>
      </div>
      
      <!-- Speed -->
      <div class="retro-card telemetry-card">
        <div class="card-header">
          <h4>VELOCITY</h4>
          <div class="speed-icon">🚀</div>
        </div>
        <div class="card-content">
          <div class="metric-value">{{ speedDisplay }} <span class="unit">{{ speedUnit }}</span></div>
          <div class="speed-trend" :class="speedTrendClass">
            {{ speedTrend > 0 ? '▲' : speedTrend < 0 ? '▼' : '▬' }} {{ Math.abs(speedTrend) }}%
          </div>
        </div>
      </div>
      
      <!-- Environmental Sensors -->
      <div class="retro-card telemetry-card environmental-card">
        <div class="card-header">
          <h4>ENVIRONMENT</h4>
          <div class="temp-icon">🌡️</div>
        </div>
        <div class="card-content">
          <div class="env-grid">
            <div class="env-metric">
              <span class="metric-label">Temp</span>
              <span class="metric-value">{{ temperatureDisplay }}<span class="unit">{{ temperatureUnit }}</span></span>
              <span class="metric-status" :class="tempStatusClass">{{ tempStatus }}</span>
            </div>
            <div class="env-metric">
              <span class="metric-label">Humidity</span>
              <span class="metric-value">{{ humidityDisplay }}<span class="unit">%</span></span>
            </div>
            <div class="env-metric">
              <span class="metric-label">Pressure</span>
              <span class="metric-value">{{ pressureDisplay }}<span class="unit">{{ pressureUnit }}</span></span>
            </div>
            <div class="env-metric">
              <span class="metric-label">Altitude</span>
              <span class="metric-value">{{ altitudeDisplay }}<span class="unit">{{ altitudeUnit }}</span></span>
            </div>
          </div>
          <div class="env-source">Source: {{ environmentalSourceLabel }}</div>
        </div>
      </div>

      <!-- ToF Sensors -->
      <div class="retro-card telemetry-card tof-card">
        <div class="card-header">
          <h4>TOF RANGE</h4>
          <div class="tof-icon">🛰️</div>
        </div>
        <div class="card-content tof-grid">
          <div class="tof-column">
            <div class="metric-label">LEFT</div>
            <div class="metric-value">{{ tofLeftDisplay }}<span class="unit">{{ tofUnit }}</span></div>
            <div class="metric-status" :class="tofStatusClass(tofLeft.status)">{{ formatTofStatus(tofLeft.status) }}</div>
          </div>
          <div class="tof-column">
            <div class="metric-label">RIGHT</div>
            <div class="metric-value">{{ tofRightDisplay }}<span class="unit">{{ tofUnit }}</span></div>
            <div class="metric-status" :class="tofStatusClass(tofRight.status)">{{ formatTofStatus(tofRight.status) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- IMU Calibration -->
    <div class="retro-card calibration-card">
      <div class="card-header">
        <h3>◢ IMU CALIBRATION ◣</h3>
        <div class="calibration-indicator" :class="calibrationStatusClass" />
      </div>
      <div class="card-content">
        <div class="calibration-row">
          <span class="metric-label">Status</span>
          <span class="metric-value">{{ imuCalibrationLabel }}</span>
        </div>
        <div class="calibration-row">
          <span class="metric-label">Score</span>
          <span class="metric-value">{{ imuCalibrationScore }} / 3</span>
        </div>
        <div class="calibration-row">
          <span class="metric-label">Last Run</span>
          <span class="metric-value">{{ lastCalibrationSummary }}</span>
        </div>
        <button class="retro-btn calibrate-btn" :disabled="imuCalibrating || !imuSupported" @click="runImuCalibration">
          <span class="btn-icon">♻</span>
          {{ !imuSupported ? 'NOT SUPPORTED' : imuCalibrating ? 'CALIBRATING…' : 'RUN CALIBRATION' }}
        </button>
        <p v-if="calibrationError" class="calibration-error">⚠ {{ calibrationError }}</p>
        <p v-else-if="!imuSupported" class="calibration-note unsupported">IMU calibration not supported on this hardware.</p>
        <p v-else-if="lastCalibration?.notes" class="calibration-note">{{ lastCalibration?.notes }}</p>
      </div>
    </div>

    <!-- Event Log -->
    <div class="retro-card events-card">
      <div class="card-header">
        <h3>◢ SYSTEM LOG ◣</h3>
        <div class="log-indicator" />
      </div>
      <div class="card-content">
        <div class="events-terminal">
          <div
            v-for="event in recentEvents"
            :key="event.id"
            class="log-entry"
            :class="event.level"
          >
            <span class="log-time">[{{ formatTime(event.timestamp) }}]</span>
            <span class="log-level">{{ event.level.toUpperCase() }}:</span>
            <span class="log-message">{{ event.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { systemApi, controlApi, telemetryApi, weatherApi, settingsApi, maintenanceApi } from '@/composables/useApi'
import { useWebSocket } from '@/services/websocket'
import { usePreferencesStore } from '@/stores/preferences'

interface TofState {
  distance: number | null
  status: string | null
  signal: number | null
}

interface ImuCalibrationResult {
  status: string
  calibration_status?: string | null
  calibration_score: number
  timestamp: string
  started_at?: string | null
  notes?: string | null
  steps: Array<Record<string, any>>
}

const { connected, connecting, connect, subscribe, unsubscribe, setCadence } = useWebSocket()

// Loading and UI state
const isLoading = ref(false)
const dataStreamText = ref('>>> INITIALIZING SYSTEM CONNECTION...')

// Preferences
const preferences = usePreferencesStore()
preferences.ensureInitialized()
const unitSystem = computed(() => preferences.unitSystem)

// Core system state
const currentMode = ref('IDLE')
const progress = ref(0)
const uptime = ref('0h 0m')
const systemStatus = ref('Unknown')
const connectionStatus = ref('Disconnected')

// Telemetry data
const gpsLatitude = ref<string | null>(null)
const gpsLongitude = ref<string | null>(null)
const gpsStatus = ref('NO SIGNAL')
const gpsAccuracy = ref<number | null>(null)
const gpsHdop = ref<number | null>(null)
const gpsSatellites = ref<number | null>(null)
const gpsRtkStatus = ref<string | null>(null)

const batteryLevel = ref(0)
const batteryVoltage = ref(0)
const speed = ref(0)
const speedTrend = ref(0)

const temperature = ref<number | null>(null)
const humidity = ref<number | null>(null)
const pressure = ref<number | null>(null)
const altitude = ref<number | null>(null)
const environmentalSource = ref<'hardware' | 'weather' | 'unknown'>('unknown')

const tofLeft = ref<TofState>({ distance: null, status: null, signal: null })
const tofRight = ref<TofState>({ distance: null, status: null, signal: null })

const imuCalibrationScore = ref(0)
const imuCalibrationStatus = ref<string>('unknown')
const imuCalibrating = ref(false)
const lastCalibration = ref<ImuCalibrationResult | null>(null)
const calibrationError = ref<string | null>(null)
const imuSupported = ref(true)
let calibrationPollHandle: number | null = null

// Event log
const recentEvents = ref([
  { id: Date.now(), timestamp: new Date(), message: 'System initializing...', level: 'info' },
])

// Computed properties for styling and display
const systemStatusClass = computed(() => {
  switch (systemStatus.value.toLowerCase()) {
    case 'active':
    case 'running':
      return 'status-active'
    case 'warning':
    case 'caution':
      return 'status-warning'
    case 'error':
    case 'critical':
      return 'status-error'
    default:
      return 'status-unknown'
  }
})

const connectionStatusClass = computed(() => {
  switch (connectionStatus.value.toLowerCase()) {
    case 'connected':
    case 'online':
      return 'status-active'
    case 'connecting':
      return 'status-warning'
    default:
      return 'status-error'
  }
})

const hasGpsFix = computed(() => gpsLatitude.value !== null && gpsLongitude.value !== null)

const gpsAccuracyUnit = computed(() => unitSystem.value === 'imperial' ? 'ft' : 'm')

const gpsAccuracyDisplay = computed(() => {
  if (gpsAccuracy.value === null) return '--'
  const base = unitSystem.value === 'imperial' ? gpsAccuracy.value * 3.28084 : gpsAccuracy.value
  return base >= 100 ? base.toFixed(0) : base.toFixed(2)
})

const gpsHdopDisplay = computed(() => {
  if (gpsHdop.value === null) return '--'
  return gpsHdop.value.toFixed(2)
})

const gpsSatellitesDisplay = computed(() => {
  if (gpsSatellites.value === null) return '--'
  return gpsSatellites.value.toString()
})

const gpsStatusClass = computed(() => {
  if (!hasGpsFix.value) return 'status-error'
  if (gpsAccuracy.value !== null && gpsAccuracy.value > 2.0) return 'status-warning'
  return 'status-active'
})

const gpsAccuracySummary = computed(() => {
  if (!hasGpsFix.value) return 'NO SIGNAL'
  if (gpsAccuracy.value === null) return 'SIGNAL ACQUIRED'
  return `Accuracy ±${gpsAccuracyDisplay.value} ${gpsAccuracyUnit.value}`
})

const batteryIconClass = computed(() => {
  if (batteryLevel.value > 50) return 'battery-high'
  if (batteryLevel.value > 20) return 'battery-medium'
  return 'battery-low'
})

const batteryBarClass = computed(() => {
  if (batteryLevel.value > 50) return 'battery-good'
  if (batteryLevel.value > 20) return 'battery-warning'
  return 'battery-critical'
})

const batteryLevelDisplay = computed(() => batteryLevel.value.toFixed(1))
const batteryVoltageDisplay = computed(() => batteryVoltage.value.toFixed(1))

const speedTrendClass = computed(() => (speedTrend.value > 0 ? 'trend-up' : speedTrend.value < 0 ? 'trend-down' : 'trend-stable'))

const speedDisplay = computed(() => {
  const value = speed.value || 0
  const converted = unitSystem.value === 'imperial' ? value * 2.23694 : value
  return converted.toFixed(1)
})

const speedUnit = computed(() => (unitSystem.value === 'imperial' ? 'mph' : 'm/s'))

const temperatureDisplay = computed(() => {
  if (temperature.value === null) return '--'
  const converted = unitSystem.value === 'imperial' ? (temperature.value * 9) / 5 + 32 : temperature.value
  return converted.toFixed(1)
})

const temperatureUnit = computed(() => (unitSystem.value === 'imperial' ? '°F' : '°C'))

const tempStatus = computed(() => {
  if (temperature.value === null) return 'UNKNOWN'
  if (temperature.value > 40) return 'CRITICAL'
  if (temperature.value > 30) return 'WARNING'
  return 'NORMAL'
})

const tempStatusClass = computed(() => {
  if (temperature.value === null) return 'status-unknown'
  if (temperature.value > 40) return 'status-error'
  if (temperature.value > 30) return 'status-warning'
  return 'status-active'
})

const humidityDisplay = computed(() => (humidity.value === null ? '--' : humidity.value.toFixed(1)))

const pressureDisplay = computed(() => {
  if (pressure.value === null) return '--'
  if (unitSystem.value === 'imperial') {
    const inHg = pressure.value * 0.0295299831
    return inHg.toFixed(2)
  }
  return pressure.value.toFixed(1)
})

const pressureUnit = computed(() => (unitSystem.value === 'imperial' ? 'inHg' : 'hPa'))

const altitudeDisplay = computed(() => {
  if (altitude.value === null) return '--'
  const converted = unitSystem.value === 'imperial' ? altitude.value * 3.28084 : altitude.value
  return converted.toFixed(1)
})

const altitudeUnit = computed(() => (unitSystem.value === 'imperial' ? 'ft' : 'm'))

const environmentalSourceLabel = computed(() => {
  switch (environmentalSource.value) {
    case 'hardware':
      return 'Hardware'
    case 'weather':
      return 'Weather service'
    default:
      return 'Unknown'
  }
})

const tofUnit = computed(() => (unitSystem.value === 'imperial' ? 'in' : 'cm'))

const formatTofDistance = (distanceMm: number | null) => {
  if (distanceMm === null) return '--'
  if (unitSystem.value === 'imperial') {
    return (distanceMm / 25.4).toFixed(1)
  }
  return (distanceMm / 10).toFixed(1)
}

const tofLeftDisplay = computed(() => formatTofDistance(tofLeft.value.distance))
const tofRightDisplay = computed(() => formatTofDistance(tofRight.value.distance))

const formatTofStatus = (status: string | null) => {
  if (!status) return 'UNKNOWN'
  return status.replace(/_/g, ' ').toUpperCase()
}

const tofStatusClass = (status: string | null) => {
  if (!status) return 'status-unknown'
  const norm = status.toLowerCase()
  if (['valid', 'ok', 'good'].includes(norm)) return 'status-active'
  if (['wrap_around', 'warning', 'calibrating'].includes(norm)) return 'status-warning'
  return 'status-error'
}

const imuCalibrationLabel = computed(() => {
  if (!imuSupported.value) return 'NOT SUPPORTED'
  if (imuCalibrating.value) return 'Calibrating…'
  if (imuCalibrationStatus.value) return imuCalibrationStatus.value.replace(/_/g, ' ').toUpperCase()
  return 'UNKNOWN'
})

const calibrationStatusClass = computed(() => {
  if (!imuSupported.value) return 'status-unknown'
  if (imuCalibrating.value) return 'status-warning'
  if (imuCalibrationScore.value >= 2) return 'status-active'
  if (imuCalibrationScore.value === 0) return 'status-error'
  return 'status-warning'
})

const lastCalibrationSummary = computed(() => {
  if (!imuSupported.value) return 'Unavailable'
  if (!lastCalibration.value) return 'Never'
  try {
    return new Date(lastCalibration.value.timestamp).toLocaleString()
  } catch (error) {
    return lastCalibration.value.timestamp
  }
})

const coerceFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed.length === 0) return undefined
    const parsed = Number(trimmed)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return undefined
}

const estimateBatteryFromVoltage = (voltage: unknown): number | null => {
  if (typeof voltage !== 'number' || Number.isNaN(voltage)) {
    return null
  }
  const minV = 11.5
  const maxV = 13.0
  if (voltage <= minV) return 0.0
  if (voltage >= maxV) return 100.0
  const pct = ((voltage - minV) / (maxV - minV)) * 100.0
  return Number.isFinite(pct) ? Number(pct.toFixed(1)) : null
}

const applyBatteryMetrics = (payload: any) => {
  if (payload === null || payload === undefined) return
  if (typeof payload === 'number') {
    const estimated = estimateBatteryFromVoltage(payload)
    if (estimated !== null) {
      batteryLevel.value = Math.max(0, Math.min(100, estimated))
    }
    batteryVoltage.value = payload
    return
  }
  if (typeof payload === 'string') {
    const numeric = coerceFiniteNumber(payload)
    if (numeric !== undefined) {
      const estimated = estimateBatteryFromVoltage(numeric)
      if (estimated !== null) {
        batteryLevel.value = Math.max(0, Math.min(100, estimated))
      }
      batteryVoltage.value = numeric
    }
    return
  }
  if (typeof payload !== 'object') return
  const battery = payload?.battery ?? payload?.power?.battery ?? payload
  const percentCandidates = [
    battery?.percentage,
    battery?.soc,
    battery?.soc_percent,
    battery?.percent,
    battery?.charge_percent,
    battery?.level,
    payload?.battery_percentage,
    payload?.battery_soc_percent,
    payload?.power?.battery_percentage,
    payload?.power?.battery_soc_percent,
  ]
  const voltageCandidates = [
    battery?.voltage,
    battery?.battery_voltage,
    battery?.pack_voltage,
    payload?.battery_voltage,
    payload?.power?.battery_voltage,
  ]

  let percent = percentCandidates
    .map((value) => coerceFiniteNumber(value))
    .find((value) => value !== undefined)
  const voltage = voltageCandidates
    .map((value) => coerceFiniteNumber(value))
    .find((value) => value !== undefined)
  if ((percent === undefined || percent === null) && voltage !== undefined) {
    const estimated = estimateBatteryFromVoltage(voltage)
    if (estimated !== null) {
      percent = estimated
    }
  }
  if (typeof percent === 'number' && !Number.isNaN(percent)) {
    const normalizedPercent = Number(percent.toFixed(1))
    batteryLevel.value = Math.max(0, Math.min(100, normalizedPercent))
  }
  if (typeof voltage === 'number' && !Number.isNaN(voltage)) {
    batteryVoltage.value = voltage
  }
}

const coerceTofReading = (reading: any): TofState => {
  if (typeof reading === 'number') {
    return Number.isFinite(reading)
      ? { distance: reading, status: null, signal: null }
      : { distance: null, status: null, signal: null }
  }
  if (typeof reading === 'string') {
    const numeric = coerceFiniteNumber(reading)
    return numeric !== undefined
      ? { distance: numeric, status: null, signal: null }
      : { distance: null, status: reading, signal: null }
  }
  if (!reading || typeof reading !== 'object') {
    return { distance: null, status: null, signal: null }
  }
  const distanceCandidates = [
    reading.distance_mm,
    reading.distance,
    reading.range,
    reading.measurement_mm,
    reading.measurement,
    reading.distance_mm_estimate,
  ]
  const distance = distanceCandidates
    .map((value) => coerceFiniteNumber(value))
    .find((value) => value !== undefined)

  const status = reading.range_status ?? reading.status ?? reading.state ?? reading.quality ?? null
  const signalCandidates = [
    reading.signal_strength,
    reading.signal_rate,
    reading.signal,
    reading.signal_strength_raw,
  ]
  const signal = signalCandidates
    .map((value) => coerceFiniteNumber(value))
    .find((value) => value !== undefined)
  return {
    distance: distance ?? null,
    status,
    signal: signal ?? null
  }
}

const applyTofMetrics = (payload: any) => {
  if (!payload) {
    tofLeft.value = coerceTofReading(null)
    tofRight.value = coerceTofReading(null)
    return
  }

  let source = payload
  if (Array.isArray(source)) {
    source = source[0] ?? {}
  }
  if (source.tof) {
    source = source.tof
  }

  const leftSrc =
    source.left ??
    source.tof_left ??
    source.left_sensor ??
    source.front_left ??
    source.left_reading ??
    source.left_distance_mm ??
    source.left_distance ??
    source.distance_left ??
    null

  const rightSrc =
    source.right ??
    source.tof_right ??
    source.right_sensor ??
    source.front_right ??
    source.right_reading ??
    source.right_distance_mm ??
    source.right_distance ??
    source.distance_right ??
    null

  if (leftSrc == null && rightSrc == null) {
    const shared =
      source.distance_mm ??
      source.distance ??
      source.range ??
      source.measurement_mm ??
      source.measurement ??
      null
    tofLeft.value = coerceTofReading(shared)
    tofRight.value = coerceTofReading(shared)
    return
  }

  tofLeft.value = coerceTofReading(leftSrc)
  tofRight.value = coerceTofReading(rightSrc)
}

watch(unitSystem, () => {
  if (hasGpsFix.value) {
    gpsStatus.value = gpsAccuracySummary.value
  }
})

// System control methods
const startSystem = async () => {
  try {
    isLoading.value = true
    addLogEntry('Initiating system startup...', 'info')
    await controlApi.start()
    currentMode.value = 'RUNNING'
    addLogEntry('System started successfully', 'success')
  } catch (error) {
    console.error('Failed to start system:', error)
    addLogEntry(`Start failed: ${error.message || 'Unknown error'}`, 'error')
  } finally {
    isLoading.value = false
  }
}

const pauseSystem = async () => {
  try {
    isLoading.value = true
    addLogEntry('Pausing system operations...', 'info')
    await controlApi.pause()
    currentMode.value = 'PAUSED'
    addLogEntry('System paused', 'warning')
  } catch (error) {
    console.error('Failed to pause system:', error)
    addLogEntry(`Pause failed: ${error.message || 'Unknown error'}`, 'error')
  } finally {
    isLoading.value = false
  }
}

const stopSystem = async () => {
  try {
    isLoading.value = true
    addLogEntry('Stopping system operations...', 'info')
    await controlApi.stop()
    currentMode.value = 'STOPPED'
    addLogEntry('System stopped', 'info')
  } catch (error) {
    console.error('Failed to stop system:', error)
    addLogEntry(`Stop failed: ${error.message || 'Unknown error'}`, 'error')
  } finally {
    isLoading.value = false
  }
}

const emergencyStop = async () => {
  try {
    isLoading.value = true
    addLogEntry('EMERGENCY STOP ACTIVATED', 'error')
    await controlApi.emergencyStop()
    currentMode.value = 'E-STOP'
    addLogEntry('Emergency stop complete - system secured', 'error')
  } catch (error) {
    console.error('Failed to emergency stop:', error)
    addLogEntry(`E-STOP FAILED: ${error.message || 'Unknown error'}`, 'error')
  } finally {
    isLoading.value = false
  }
}

// Utility methods
const formatTime = (timestamp: Date) => {
  return timestamp.toLocaleTimeString('en-US', { hour12: false })
}

const addLogEntry = (message: string, level: 'info' | 'success' | 'warning' | 'error') => {
  recentEvents.value.unshift({
    id: Date.now() + Math.random(),
    timestamp: new Date(),
    message,
    level
  })
  // Keep only last 10 entries
  if (recentEvents.value.length > 10) {
    recentEvents.value = recentEvents.value.slice(0, 10)
  }
}

const loadUnitPreference = async () => {
  try {
    const settings = await settingsApi.getSettings()
    const systemPrefs = settings?.system ?? settings?.categories?.system ?? {}
    const preference = typeof systemPrefs?.unit_system === 'string' ? systemPrefs.unit_system.toLowerCase() : null
    if (preference === 'metric' || preference === 'imperial') {
      preferences.setUnitSystem(preference)
    }
  } catch (error) {
    console.error('Failed to load unit preference:', error)
  }
}

const applyCalibrationResult = (result: ImuCalibrationResult) => {
  lastCalibration.value = result
  imuCalibrationStatus.value = result.calibration_status ?? result.status
  imuCalibrationScore.value = typeof result.calibration_score === 'number' ? result.calibration_score : 0
}

const stopCalibrationPolling = () => {
  if (calibrationPollHandle !== null) {
    window.clearInterval(calibrationPollHandle)
    calibrationPollHandle = null
  }
}

const handleImuUnsupported = () => {
  if (!imuSupported.value) return
  imuSupported.value = false
  imuCalibrating.value = false
  stopCalibrationPolling()
  imuCalibrationStatus.value = 'not_supported'
  imuCalibrationScore.value = 0
  lastCalibration.value = null
  calibrationError.value = null
  addLogEntry('IMU calibration not supported on this hardware.', 'warning')
}

const refreshCalibrationStatus = async () => {
  try {
    const status = await maintenanceApi.getImuCalibrationStatus()
    imuSupported.value = true
    calibrationError.value = null
    imuCalibrating.value = Boolean(status.in_progress)
    if (status.last_result) {
      applyCalibrationResult(status.last_result)
    }
    if (status.in_progress) {
      if (calibrationPollHandle === null) {
        calibrationPollHandle = window.setInterval(refreshCalibrationStatus, 2000)
      }
    } else {
      stopCalibrationPolling()
    }
  } catch (error) {
    const responseStatus = (error as any)?.response?.status
    if (responseStatus === 404) {
      handleImuUnsupported()
      return
    }
    console.error('Failed to fetch calibration status:', error)
  }
}

const runImuCalibration = async () => {
  if (imuCalibrating.value) return
  if (!imuSupported.value) {
    addLogEntry('IMU calibration requested but hardware reports it is unsupported.', 'warning')
    calibrationError.value = null
    return
  }
  imuCalibrating.value = true
  calibrationError.value = null
  addLogEntry('Starting IMU calibration routine…', 'info')
  if (calibrationPollHandle === null) {
    calibrationPollHandle = window.setInterval(refreshCalibrationStatus, 2000)
  }
  try {
    const result = await maintenanceApi.runImuCalibration()
    applyCalibrationResult(result)
    const level = result.calibration_score >= 2 ? 'success' : 'warning'
    const message = result.calibration_score >= 2
      ? 'IMU calibration completed successfully'
      : 'IMU calibration incomplete—continue motion for better score'
    addLogEntry(message, level)
  } catch (error: any) {
    const responseStatus = error?.response?.status
    if (responseStatus === 404) {
      handleImuUnsupported()
      return
    }
    const detail = error?.response?.data?.detail || error?.message || 'Calibration failed'
    calibrationError.value = detail
    addLogEntry(`IMU calibration failed: ${detail}`, 'error')
  } finally {
    if (imuSupported.value) {
      await refreshCalibrationStatus()
    } else {
      imuCalibrating.value = false
    }
  }
}

// Data loading methods
const loadSystemStatus = async () => {
  try {
    const status = await systemApi.getStatus()
    systemStatus.value = status.status || 'Unknown'
    uptime.value = status.uptime || '0h 0m'
    connectionStatus.value = 'Connected'
    dataStreamText.value = '>>> SYSTEM ONLINE - DATA STREAMING ACTIVE'
  } catch (error) {
    console.error('Failed to load system status:', error)
    systemStatus.value = 'Error'
    connectionStatus.value = 'Disconnected'
    dataStreamText.value = '>>> CONNECTION LOST - ATTEMPTING RECONNECT...'
  }
}

const loadTelemetryData = async () => {
  try {
    const telemetry = await telemetryApi.getCurrent()
    
    // Update battery data
    applyBatteryMetrics(telemetry)
    
    // Update GPS data
    const lat = telemetry.position?.latitude
    const lon = telemetry.position?.longitude
    if (typeof lat === 'number' && typeof lon === 'number') {
      gpsLatitude.value = lat.toFixed(6)
      gpsLongitude.value = lon.toFixed(6)
      gpsAccuracy.value = typeof telemetry.position?.accuracy === 'number' ? telemetry.position.accuracy : null
      gpsHdop.value = typeof telemetry.position?.hdop === 'number' ? telemetry.position.hdop : null
      gpsSatellites.value = typeof telemetry.position?.satellites === 'number' ? telemetry.position.satellites : null
      gpsRtkStatus.value = telemetry.position?.rtk_status ?? null
      gpsStatus.value = gpsAccuracySummary.value
    } else {
      gpsLatitude.value = null
      gpsLongitude.value = null
      gpsAccuracy.value = null
      gpsHdop.value = null
      gpsSatellites.value = null
      gpsRtkStatus.value = null
      gpsStatus.value = 'SEARCHING...'
    }
    
    const speedValue = telemetry.position?.speed ?? telemetry.speed_mps
    if (typeof speedValue === 'number') {
      const delta = speedValue - speed.value
      speedTrend.value = speed.value > 0.1 ? (delta / speed.value) * 100 : 0
      speed.value = speedValue
    }

    // Update environmental data
    if (telemetry.environmental) {
      const env = telemetry.environmental
      temperature.value = typeof env.temperature_c === 'number' ? env.temperature_c : null
      humidity.value = typeof env.humidity_percent === 'number' ? env.humidity_percent : null
      pressure.value = typeof env.pressure_hpa === 'number' ? env.pressure_hpa : null
      altitude.value = typeof env.altitude_m === 'number' ? env.altitude_m : null
      environmentalSource.value = 'hardware'
    }

    // Update ToF data
    applyTofMetrics(telemetry)

    // Update IMU calibration snapshot
    if (telemetry.imu) {
      imuCalibrationScore.value = telemetry.imu.calibration ?? 0
      imuCalibrationStatus.value = telemetry.imu.calibration_status ?? 'unknown'
    }

    // Update motor status
    if (telemetry.motor_status) {
      currentMode.value = telemetry.motor_status.toUpperCase()
    }
    
  } catch (error) {
    console.error('Failed to load telemetry:', error)
    addLogEntry('Telemetry data unavailable', 'warning')
  }
}

const loadWeatherData = async () => {
  try {
    const weather = await weatherApi.getCurrent()
    if (typeof weather.temperature_c === 'number' && temperature.value === null) {
      temperature.value = weather.temperature_c
      environmentalSource.value = 'weather'
    }
    if (typeof weather.humidity_percent === 'number' && humidity.value === null) {
      humidity.value = weather.humidity_percent
    }
    if (pressure.value === null && (weather as any)?.pressure_hpa !== undefined) {
      const pressureValue = Number((weather as any).pressure_hpa)
      if (!Number.isNaN(pressureValue)) {
        pressure.value = pressureValue
      }
    }
  } catch (error) {
    console.error('Failed to load weather:', error)
  }
}

// Component lifecycle and data initialization
onMounted(async () => {
  addLogEntry('Dashboard initializing...', 'info')
  
  // Load initial data
  await Promise.all([
    loadUnitPreference(),
    loadSystemStatus(),
    loadTelemetryData(),
    loadWeatherData(),
    refreshCalibrationStatus()
  ])
  
  // Connect to WebSocket for real-time updates
  try {
    addLogEntry('Establishing WebSocket connection...', 'info')
    await connect()
    
    if (connected.value) {
      addLogEntry('WebSocket connected - subscribing to telemetry feeds', 'success')
      
      // Subscribe to telemetry topics with real data handling
      subscribe('telemetry.power', (data) => {
        applyBatteryMetrics(data)
        dataStreamText.value = `>>> POWER: ${batteryLevelDisplay.value}% | ${batteryVoltageDisplay.value}V`
      })
      
      subscribe('telemetry.navigation', (data) => {
        const lat = data.position?.latitude
        const lon = data.position?.longitude
        if (typeof lat === 'number' && typeof lon === 'number') {
          gpsLatitude.value = lat.toFixed(6)
          gpsLongitude.value = lon.toFixed(6)
          gpsAccuracy.value = typeof data.position?.accuracy === 'number' ? data.position.accuracy : null
          gpsHdop.value = typeof (data.hdop ?? data.position?.hdop) === 'number' ? (data.hdop ?? data.position?.hdop) : null
          gpsSatellites.value = typeof data.position?.satellites === 'number' ? data.position.satellites : null
          gpsRtkStatus.value = data.position?.rtk_status ?? null
          gpsStatus.value = gpsAccuracySummary.value
        } else {
          gpsLatitude.value = null
          gpsLongitude.value = null
          gpsAccuracy.value = null
          gpsHdop.value = null
          gpsSatellites.value = null
          gpsRtkStatus.value = null
          gpsStatus.value = 'SEARCHING...'
        }
        
        const navSpeed = typeof data.speed_mps === 'number' ? data.speed_mps : typeof data.position?.speed === 'number' ? data.position.speed : null
        if (navSpeed !== null) {
          const newSpeed = navSpeed
          speedTrend.value = speed.value > 0.1 ? ((newSpeed - speed.value) / speed.value) * 100 : 0
          speed.value = newSpeed
        }
      })
      
      subscribe('telemetry.motors', (data) => {
        if (data.motor_status) {
          currentMode.value = data.motor_status.toUpperCase()
          addLogEntry(`Motor status: ${data.motor_status}`, 'info')
        }
      })
      
      subscribe('telemetry.system', (data) => {
        if (data.uptime_seconds) {
          const uptimeSeconds = data.uptime_seconds
          const hours = Math.floor(uptimeSeconds / 3600)
          const minutes = Math.floor((uptimeSeconds % 3600) / 60)
          uptime.value = `${hours}h ${minutes}m`
        }
        
        if (data.safety_state) {
          if (data.safety_state === 'nominal' || data.safety_state === 'safe') {
            systemStatus.value = 'Active'
          } else if (data.safety_state === 'emergency_stop') {
            systemStatus.value = 'Emergency Stop'
          } else {
            systemStatus.value = 'Warning'
          }
        }
      })
      
      subscribe('telemetry.weather', (data) => {
        if (data.temperature_c !== undefined) {
          temperature.value = data.temperature_c
          environmentalSource.value = 'weather'
        }
        if (data.humidity_percent !== undefined) {
          humidity.value = data.humidity_percent
        }
      })

      subscribe('telemetry.environmental', (data) => {
        const env = data.environmental || {}
        if (env.temperature_c !== undefined) {
          temperature.value = env.temperature_c
        }
        if (env.humidity_percent !== undefined) {
          humidity.value = env.humidity_percent
        }
        if (env.pressure_hpa !== undefined) {
          pressure.value = env.pressure_hpa
        }
        if (env.altitude_m !== undefined) {
          altitude.value = env.altitude_m
        }
        environmentalSource.value = 'hardware'
      })

      subscribe('telemetry.tof', (data) => {
        applyTofMetrics(data)
      })

      subscribe('telemetry.sensors', (data) => {
        if (data.imu) {
          imuCalibrationScore.value = data.imu.calibration ?? imuCalibrationScore.value
          imuCalibrationStatus.value = data.imu.calibration_status ?? imuCalibrationStatus.value
        }
        if (data.tof) {
          applyTofMetrics(data)
        }
      })
      
      subscribe('jobs.progress', (data) => {
        if (data.progress_percent !== undefined) {
          progress.value = data.progress_percent
        }
        if (data.current_job && data.status) {
          const status = data.status === 'running' ? `RUNNING: ${data.current_job}` : 'IDLE'
          if (currentMode.value !== status) {
            currentMode.value = status
            addLogEntry(`Job status: ${status}`, 'info')
          }
        }
      })
      
      // Set telemetry cadence to 5Hz for real-time dashboard
      setTimeout(() => {
        setCadence(5)
        addLogEntry('Telemetry cadence set to 5Hz', 'info')
      }, 1000)
      
    } else {
      addLogEntry('WebSocket connection failed - using polling mode', 'warning')
    }
  } catch (error) {
    console.error('WebSocket connection error:', error)
    addLogEntry('WebSocket unavailable - using REST API only', 'warning')
  }
  
  // Set up periodic data refresh for fallback
  const refreshInterval = setInterval(async () => {
    if (!connected.value) {
      await Promise.all([
        loadUnitPreference(),
        loadSystemStatus(),
        loadTelemetryData(),
        loadWeatherData()
      ])
    }
  }, 2000) // 0.5Hz fallback rate
  
  // Cleanup on unmount
  onUnmounted(() => {
    clearInterval(refreshInterval)
    stopCalibrationPolling()
    if (connected.value) {
      unsubscribe('telemetry.power')
      unsubscribe('telemetry.navigation')  
      unsubscribe('telemetry.motors')
      unsubscribe('telemetry.system')
      unsubscribe('telemetry.weather')
      unsubscribe('telemetry.environmental')
      unsubscribe('telemetry.tof')
      unsubscribe('telemetry.sensors')
      unsubscribe('jobs.progress')
    }
  })
})
</script>

<style scoped>
/* 1980s Retro Dashboard Styling */
.retro-dashboard {
  padding: 0;
  background: #0a0a0a;
  color: #00ffff;
  font-family: 'Courier New', 'Consolas', monospace;
  min-height: 100vh;
}

/* Retro Header */
.retro-header {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d1b69 30%, #8b0057 70%, #0d0d0d 100%);
  padding: 2rem;
  margin-bottom: 2rem;
  border: 2px solid #00ffff;
  border-left: 5px solid #ff00ff;
  border-right: 5px solid #ffff00;
  position: relative;
  overflow: hidden;
}

.header-glow {
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(0, 255, 255, 0.3), rgba(255, 0, 255, 0.3), transparent);
  animation: scanline 4s linear infinite;
}

@keyframes scanline {
  0% { left: -100%; }
  100% { left: 100%; }
}

.retro-title {
  font-size: 3rem;
  font-weight: 900;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 8px;
  margin: 0 0 0.5rem 0;
  font-family: 'Orbitron', 'Courier New', monospace;
  background: linear-gradient(45deg, #00ffff, #ff00ff, #ffff00, #00ffff);
  background-size: 400% 400%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: titleGlow 4s ease-in-out infinite;
  text-shadow: 0 0 30px rgba(0, 255, 255, 0.8), 0 0 60px rgba(255, 0, 255, 0.4);
  position: relative;
}

.retro-title::before {
  content: attr(data-text);
  position: absolute;
  top: 2px;
  left: 2px;
  z-index: -1;
  background: linear-gradient(45deg, #ff00ff, #00ffff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  opacity: 0.3;
  animation: glitchShadow 5s ease-in-out infinite;
}

@keyframes glitchShadow {
  0%, 100% { transform: translate(0, 0); }
  20% { transform: translate(-2px, 2px); }
  40% { transform: translate(2px, -1px); }
  60% { transform: translate(-1px, -2px); }
  80% { transform: translate(1px, 1px); }
}

@keyframes titleGlow {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.retro-subtitle {
  text-align: center;
  font-size: 1.1rem;
  font-weight: 600;
  letter-spacing: 4px;
  color: #ffff00;
  margin: 0 0 1.5rem 0;
  font-family: 'Orbitron', 'Courier New', monospace;
  text-shadow: 0 0 15px rgba(255, 255, 0, 0.8), 0 0 30px rgba(255, 255, 0, 0.4);
  text-transform: uppercase;
  position: relative;
}

.retro-subtitle::after {
  content: '';
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translateX(-50%);
  width: 200px;
  height: 2px;
  background: linear-gradient(90deg, transparent, #ffff00, transparent);
  animation: subtitleLine 3s ease-in-out infinite;
}

@keyframes subtitleLine {
  0%, 100% { opacity: 0.6; width: 200px; }
  50% { opacity: 1; width: 300px; }
}

@keyframes metricUnderline {
  0%, 100% { opacity: 0.4; transform: scaleX(0.8); }
  50% { opacity: 0.8; transform: scaleX(1.2); }
}

.data-stream {
  font-size: 0.95rem;
  text-align: center;
  color: #00ff00;
  font-family: 'Courier New', monospace;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  animation: dataStream 3s ease-in-out infinite;
  position: relative;
  background: rgba(0, 255, 0, 0.05);
  padding: 0.5rem 1rem;
  border: 1px solid rgba(0, 255, 0, 0.3);
  border-radius: 4px;
  backdrop-filter: blur(5px);
}

.data-stream::before {
  content: '▶ ';
  animation: blink 1s linear infinite;
}

.data-stream::after {
  content: ' ◀';
  animation: blink 1s linear infinite reverse;
}

@keyframes dataStream {
  0%, 100% { 
    opacity: 0.8; 
    text-shadow: 0 0 10px rgba(0, 255, 0, 0.5);
  }
  50% { 
    opacity: 1; 
    text-shadow: 0 0 20px rgba(0, 255, 0, 0.8), 0 0 30px rgba(0, 255, 0, 0.4);
  }
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0.3; }
}

@keyframes textPulse {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}

/* Dashboard Grid Layout */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.gps-metrics {
  margin-top: 1rem;
  display: grid;
  gap: 0.35rem;
  font-size: 0.85rem;
  letter-spacing: 1px;
}

.gps-metrics .metric-line span {
  color: #ffff00;
  margin-left: 0.5rem;
}

/* Retro Cards */
.retro-card {
  background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 30%, #16213e 70%, #0a0a0a 100%);
  border: 2px solid #00ffff;
  border-radius: 8px;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(10px);
  box-shadow: 
    0 8px 32px rgba(0, 255, 255, 0.3),
    0 0 20px rgba(0, 255, 255, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.1),
    inset 0 0 30px rgba(0, 255, 255, 0.05);
  transition: all 0.3s ease;
}

.retro-card:hover {
  transform: translateY(-4px);
  box-shadow: 
    0 12px 40px rgba(0, 255, 255, 0.4),
    0 0 30px rgba(0, 255, 255, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.2),
    inset 0 0 40px rgba(0, 255, 255, 0.1);
  border-color: #00ffff;
}

.retro-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00ffff, transparent);
  animation: borderScan 3s linear infinite;
}

@keyframes borderScan {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.card-header {
  background: rgba(0, 255, 255, 0.1);
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #00ffff;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3, .card-header h4 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 2px;
  color: #00ffff;
  text-shadow: 0 0 10px rgba(0, 255, 255, 0.7);
}

.card-content {
  padding: 1.5rem;
}

.environmental-card .env-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
}

.environmental-card .env-metric .metric-label {
  display: block;
  font-size: 0.8rem;
  letter-spacing: 2px;
  color: #00ffff;
  margin-bottom: 0.25rem;
}

.environmental-card .env-metric .metric-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #ffff00;
}

.environmental-card .env-metric .metric-status {
  font-size: 0.75rem;
  letter-spacing: 1px;
  display: inline-block;
  margin-top: 0.35rem;
}

.environmental-card .env-source {
  margin-top: 1rem;
  font-size: 0.75rem;
  letter-spacing: 2px;
  color: rgba(0, 255, 255, 0.7);
  text-transform: uppercase;
}

.tof-card .tof-grid {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
  justify-content: space-between;
}

.tof-card .tof-column {
  flex: 1 1 150px;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tof-card .metric-label {
  font-size: 0.8rem;
  letter-spacing: 2px;
  color: #00ffff;
}

.tof-card .metric-value {
  font-size: 1.3rem;
  font-weight: 700;
  color: #ffff00;
}

.tof-card .metric-status {
  font-size: 0.8rem;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.calibration-card {
  margin-bottom: 2rem;
}

.calibration-card .card-header {
  align-items: center;
}

.calibration-indicator {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #666;
  box-shadow: 0 0 15px currentColor;
}

.calibration-indicator.status-active {
  background: #00ff00;
  color: #00ff00;
}

.calibration-indicator.status-warning {
  background: #ffff00;
  color: #ffff00;
}

.calibration-indicator.status-error {
  background: #ff0040;
  color: #ff0040;
}

.calibration-indicator.status-unknown {
  background: #888;
  color: #888;
}

.calibration-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: 'Courier New', monospace;
  letter-spacing: 1px;
  margin-bottom: 0.75rem;
  text-transform: uppercase;
}

.calibration-row .metric-value {
  color: #ffff00;
  font-weight: 700;
}

.calibrate-btn {
  margin-top: 1rem;
  width: 100%;
  background: rgba(0, 255, 255, 0.1);
  border: 1px solid #00ffff;
}

.calibrate-btn:hover:not(:disabled) {
  background: rgba(0, 255, 255, 0.2);
}

.calibration-error {
  margin-top: 0.75rem;
  color: #ff4343;
  font-size: 0.85rem;
  letter-spacing: 1px;
}

.calibration-note {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: rgba(0, 255, 255, 0.7);
  letter-spacing: 1px;
}

.calibration-note.unsupported {
  color: rgba(255, 255, 0, 0.9);
  text-transform: uppercase;
}

/* Status Indicators */
.status-indicator, .power-indicator, .activity-pulse, .log-indicator {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #666;
  box-shadow: 0 0 15px currentColor;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
}

.status-indicator.active, .power-indicator.active {
  background: #00ff00;
  color: #00ff00;
}

.status-indicator.warning {
  background: #ffff00;
  color: #ffff00;
}

.status-indicator.error {
  background: #ff0040;
  color: #ff0040;
}

.activity-pulse {
  background: #ff00ff;
  color: #ff00ff;
}

.log-indicator {
  background: #00ffff;
  color: #00ffff;
}

/* Status Display */
.status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid rgba(0, 255, 255, 0.2);
}

.status-row:last-child {
  border-bottom: none;
}

.status-label {
  font-weight: 700;
  letter-spacing: 1px;
  color: #ffff00;
  text-shadow: 0 0 5px rgba(255, 255, 0, 0.5);
}

.status-value {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.status-value.status-active, .status-value.uptime {
  color: #00ff00;
  text-shadow: 0 0 10px rgba(0, 255, 0, 0.7);
}

.status-value.status-warning {
  color: #ffff00;
  text-shadow: 0 0 10px rgba(255, 255, 0, 0.7);
}

.status-value.status-error {
  color: #ff0040;
  text-shadow: 0 0 10px rgba(255, 0, 64, 0.7);
}

.status-value.status-unknown {
  color: #666;
}

/* Control Panel */
.control-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.retro-btn {
  background: linear-gradient(135deg, #1a1a2e, #16213e, #0f0f23);
  border: 2px solid #00ffff;
  color: #00ffff;
  padding: 1.2rem 1.5rem;
  font-family: 'Orbitron', 'Courier New', monospace;
  font-weight: 700;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 2px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  backdrop-filter: blur(10px);
  box-shadow: 
    0 4px 15px rgba(0, 255, 255, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.retro-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s ease;
}

.retro-btn:hover::before {
  left: 100%;
}

.retro-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #00ffff, #0a0a0a);
  color: #000;
  box-shadow: 0 0 20px rgba(0, 255, 255, 0.8);
  text-shadow: none;
}

.retro-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.retro-btn.start-btn:hover:not(:disabled) {
  border-color: #00ff00;
  background: linear-gradient(135deg, #00ff00, #0a0a0a);
}

.retro-btn.pause-btn:hover:not(:disabled) {
  border-color: #ffff00;
  background: linear-gradient(135deg, #ffff00, #0a0a0a);
}

.retro-btn.stop-btn:hover:not(:disabled) {
  border-color: #ff6600;
  background: linear-gradient(135deg, #ff6600, #0a0a0a);
}

.retro-btn.emergency-btn:hover:not(:disabled) {
  border-color: #ff0040;
  background: linear-gradient(135deg, #ff0040, #0a0a0a);
  animation: emergencyFlash 0.5s ease-in-out infinite;
}

@keyframes emergencyFlash {
  0%, 100% { box-shadow: 0 0 20px rgba(255, 0, 64, 0.8); }
  50% { box-shadow: 0 0 40px rgba(255, 0, 64, 1); }
}

.btn-icon {
  margin-right: 0.5rem;
  font-size: 1.2rem;
}

.mode-display {
  text-align: center;
  padding: 1rem;
  background: rgba(0, 255, 255, 0.1);
  border: 1px solid rgba(0, 255, 255, 0.3);
  margin-top: 1rem;
  font-weight: 700;
  letter-spacing: 2px;
  color: #ffff00;
}

.mode-value {
  color: #00ffff;
  text-shadow: 0 0 10px rgba(0, 255, 255, 0.7);
}

/* Progress Display */
.progress-container {
  text-align: center;
}

.progress-label {
  font-size: 2rem;
  font-weight: 900;
  color: #00ffff;
  margin-bottom: 1rem;
  text-shadow: 0 0 15px rgba(0, 255, 255, 0.7);
  letter-spacing: 2px;
}

.retro-progress {
  position: relative;
  height: 30px;
  background: #1a1a1a;
  border: 2px solid #00ffff;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #00ffff, #ff00ff, #00ff00);
  background-size: 200% 100%;
  animation: progressGlow 2s linear infinite;
  transition: width 0.5s ease;
}

@keyframes progressGlow {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.progress-grid {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: repeating-linear-gradient(
    90deg,
    transparent,
    transparent 9px,
    rgba(0, 255, 255, 0.3) 10px
  );
}

/* Telemetry Cards */
.telemetry-card .card-content {
  text-align: center;
}

.metric-value {
  font-size: 2.8rem;
  font-weight: 900;
  color: #00ffff;
  font-family: 'Orbitron', 'Courier New', monospace;
  text-shadow: 
    0 0 20px rgba(0, 255, 255, 0.8),
    0 0 40px rgba(0, 255, 255, 0.4),
    0 2px 4px rgba(0, 0, 0, 0.8);
  margin-bottom: 0.8rem;
  letter-spacing: 3px;
  position: relative;
  text-transform: uppercase;
}

.metric-value::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00ffff, transparent);
  opacity: 0.6;
  animation: metricUnderline 2s ease-in-out infinite;
}

.metric-value .unit {
  font-size: 1.5rem;
  color: #ffff00;
}

.metric-status {
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.gps-value {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: flex-end;
  gap: 1.5rem;
  font-size: 1.6rem;
  letter-spacing: 1px;
  text-transform: none;
  text-shadow: none;
}

.gps-value::after {
  display: none;
}

.gps-value .coord {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  min-width: 140px;
  font-family: 'Courier New', monospace;
  color: #ffff00;
  text-shadow: 0 0 12px rgba(255, 255, 0, 0.5);
}

.gps-value .coord-label {
  font-size: 0.75rem;
  letter-spacing: 2px;
  color: #00ffff;
  text-shadow: 0 0 8px rgba(0, 255, 255, 0.5);
  margin-bottom: 0.35rem;
}

.gps-value .coord-value {
  font-size: 1.9rem;
  letter-spacing: 0.5px;
}

.gps-value .coord.no-fix {
  align-items: center;
  font-size: 1.4rem;
  letter-spacing: 2px;
  color: #ff0040;
  text-shadow: 0 0 12px rgba(255, 0, 64, 0.6);
}

.gps-icon, .battery-icon, .speed-icon, .temp-icon {
  font-size: 1.5rem;
  filter: drop-shadow(0 0 10px currentColor);
}

/* Battery Specific */
.battery-card .metric-value {
  color: #00ff00;
  text-shadow: 0 0 15px rgba(0, 255, 0, 0.7);
}

.battery-bar {
  position: relative;
  height: 20px;
  background: #1a1a1a;
  border: 2px solid #00ffff;
  margin: 1rem 0;
  overflow: hidden;
}

.battery-fill {
  height: 100%;
  transition: width 0.5s ease;
}

.battery-fill.battery-good {
  background: linear-gradient(90deg, #00ff00, #00ffff);
}

.battery-fill.battery-warning {
  background: linear-gradient(90deg, #ffff00, #ff6600);
}

.battery-fill.battery-critical {
  background: linear-gradient(90deg, #ff0040, #ff6600);
  animation: batteryWarning 1s ease-in-out infinite;
}

@keyframes batteryWarning {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.battery-segments {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: repeating-linear-gradient(
    90deg,
    transparent,
    transparent 18px,
    rgba(0, 255, 255, 0.5) 20px
  );
}

.battery-icon.battery-high {
  color: #00ff00;
}

.battery-icon.battery-medium {
  color: #ffff00;
}

.battery-icon.battery-low {
  color: #ff0040;
  animation: batteryLowBlink 1s ease-in-out infinite;
}

@keyframes batteryLowBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Speed Trends */
.speed-trend {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 1px;
}

.speed-trend.trend-up {
  color: #00ff00;
  text-shadow: 0 0 10px rgba(0, 255, 0, 0.7);
}

.speed-trend.trend-down {
  color: #ff0040;
  text-shadow: 0 0 10px rgba(255, 0, 64, 0.7);
}

.speed-trend.trend-stable {
  color: #ffff00;
  text-shadow: 0 0 10px rgba(255, 255, 0, 0.7);
}

/* Event Log */
.events-card {
  grid-column: 1 / -1;
}

.events-terminal {
  background: #000;
  border: 2px solid #00ffff;
  padding: 1rem;
  max-height: 300px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
}

.log-entry {
  display: flex;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  line-height: 1.4;
}

.log-time {
  color: #666;
  margin-right: 1rem;
  min-width: 80px;
}

.log-level {
  margin-right: 1rem;
  min-width: 60px;
  font-weight: 700;
}

.log-entry.info .log-level {
  color: #00ffff;
}

.log-entry.success .log-level {
  color: #00ff00;
}

.log-entry.warning .log-level {
  color: #ffff00;
}

.log-entry.error .log-level {
  color: #ff0040;
  animation: errorBlink 2s ease-in-out infinite;
}

@keyframes errorBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.log-message {
  flex: 1;
  color: #00ffff;
}

/* Responsive Design */
@media (max-width: 768px) {
  .retro-title {
    font-size: 1.8rem;
    letter-spacing: 3px;
  }
  
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
  
  .telemetry-grid {
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }
  
  .control-grid {
    grid-template-columns: 1fr;
  }
  
  .metric-value {
    font-size: 2rem;
  }
  
  .retro-header {
    padding: 1rem;
  }
  
  .card-content {
    padding: 1rem;
  }
}

@media (max-width: 480px) {
  .retro-title {
    font-size: 1.5rem;
    letter-spacing: 2px;
  }
  
  .telemetry-grid {
    grid-template-columns: 1fr;
  }
  
  .metric-value {
    font-size: 1.8rem;
  }
  
  .progress-label {
    font-size: 1.5rem;
  }
}
</style>
<template>
  <div class="dashboard retro-dashboard">
    <!-- Retro Header -->
    <div class="retro-header">
      <div class="header-glow"></div>
      <h1 class="retro-title">SYSTEM DASHBOARD</h1>
      <p class="retro-subtitle">REAL-TIME MONITORING & CONTROL INTERFACE</p>
      <div class="data-stream">{{ dataStreamText }}</div>
    </div>

    <div class="dashboard-grid">
      <!-- System Status -->
      <div class="retro-card status-card">
        <div class="card-header">
          <h3>◢ SYSTEM STATUS ◣</h3>
          <div class="status-indicator" :class="systemStatusClass"></div>
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
          <div class="power-indicator" :class="{ active: currentMode !== 'IDLE' }"></div>
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
          <div class="activity-pulse"></div>
        </div>
        <div class="card-content">
          <div class="progress-container">
            <div class="progress-label">{{ progress }}% COMPLETE</div>
            <div class="retro-progress">
              <div class="progress-bar" :style="{ width: `${progress}%` }"></div>
              <div class="progress-grid"></div>
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
          <div class="metric-value">{{ gpsPosition }}</div>
          <div class="metric-status" :class="gpsStatusClass">{{ gpsStatus }}</div>
        </div>
      </div>
      
      <!-- Battery Level -->
      <div class="retro-card telemetry-card battery-card">
        <div class="card-header">
          <h4>POWER LEVEL</h4>
          <div class="battery-icon" :class="batteryIconClass">🔋</div>
        </div>
        <div class="card-content">
          <div class="metric-value">{{ batteryLevel.toFixed(1) }}%</div>
          <div class="battery-bar">
            <div class="battery-fill" :style="{ width: `${batteryLevel}%` }" :class="batteryBarClass"></div>
            <div class="battery-segments"></div>
          </div>
          <div class="metric-status">{{ batteryVoltage }}V</div>
        </div>
      </div>
      
      <!-- Speed -->
      <div class="retro-card telemetry-card">
        <div class="card-header">
          <h4>VELOCITY</h4>
          <div class="speed-icon">🚀</div>
        </div>
        <div class="card-content">
          <div class="metric-value">{{ speed.toFixed(1) }} <span class="unit">m/s</span></div>
          <div class="speed-trend" :class="speedTrendClass">
            {{ speedTrend > 0 ? '▲' : speedTrend < 0 ? '▼' : '▬' }} {{ Math.abs(speedTrend) }}%
          </div>
        </div>
      </div>
      
      <!-- Temperature -->
      <div class="retro-card telemetry-card">
        <div class="card-header">
          <h4>TEMPERATURE</h4>
          <div class="temp-icon">🌡️</div>
        </div>
        <div class="card-content">
          <div class="metric-value">{{ temperature.toFixed(1) }}<span class="unit">°C</span></div>
          <div class="temp-status" :class="tempStatusClass">{{ tempStatus }}</div>
        </div>
      </div>
    </div>

    <!-- Event Log -->
    <div class="retro-card events-card">
      <div class="card-header">
        <h3>◢ SYSTEM LOG ◣</h3>
        <div class="log-indicator"></div>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { systemApi, controlApi, telemetryApi, weatherApi } from '@/composables/useApi'
import { useWebSocket } from '@/services/websocket'

const { connected, connecting, connect, subscribe, unsubscribe } = useWebSocket()

// Loading and UI state
const isLoading = ref(false)
const dataStreamText = ref('>>> INITIALIZING SYSTEM CONNECTION...')

// Core system state
const currentMode = ref('IDLE')
const progress = ref(0)
const uptime = ref('0h 0m')
const systemStatus = ref('Unknown')
const connectionStatus = ref('Disconnected')

// Telemetry data
const gpsPosition = ref('N/A')
const gpsStatus = ref('NO SIGNAL')
const batteryLevel = ref(0)
const batteryVoltage = ref(0)
const speed = ref(0.0)
const speedTrend = ref(0)
const temperature = ref(0.0)

// Event log
const recentEvents = ref([
  { id: Date.now(), timestamp: new Date(), message: 'System initializing...', level: 'info' },
])

// Computed properties for styling
const systemStatusClass = computed(() => {
  switch (systemStatus.value.toLowerCase()) {
    case 'active': case 'running': return 'status-active'
    case 'warning': case 'caution': return 'status-warning'
    case 'error': case 'critical': return 'status-error'
    default: return 'status-unknown'
  }
})

const connectionStatusClass = computed(() => {
  switch (connectionStatus.value.toLowerCase()) {
    case 'connected': case 'online': return 'status-active'
    case 'connecting': return 'status-warning'
    default: return 'status-error'
  }
})

const gpsStatusClass = computed(() => {
  if (gpsPosition.value !== 'N/A' && !gpsPosition.value.includes('NO')) return 'status-active'
  return 'status-error'
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

const speedTrendClass = computed(() => speedTrend.value > 0 ? 'trend-up' : speedTrend.value < 0 ? 'trend-down' : 'trend-stable')

const tempStatus = computed(() => {
  if (temperature.value > 40) return 'CRITICAL'
  if (temperature.value > 30) return 'WARNING'
  return 'NORMAL'
})

const tempStatusClass = computed(() => {
  if (temperature.value > 40) return 'status-error'
  if (temperature.value > 30) return 'status-warning'
  return 'status-active'
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
    if (telemetry.battery) {
      batteryLevel.value = telemetry.battery.percentage || 0
      batteryVoltage.value = telemetry.battery.voltage || 0
    }
    
    // Update GPS data
    if (telemetry.position && telemetry.position.latitude && telemetry.position.longitude) {
      gpsPosition.value = `${telemetry.position.latitude.toFixed(6)}, ${telemetry.position.longitude.toFixed(6)}`
      gpsStatus.value = 'SIGNAL ACQUIRED'
    } else {
      gpsPosition.value = 'NO SIGNAL'
      gpsStatus.value = 'SEARCHING...'
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
    temperature.value = weather.temperature_c || 0
  } catch (error) {
    console.error('Failed to load weather:', error)
  }
}

// Component lifecycle and data initialization
onMounted(async () => {
  addLogEntry('Dashboard initializing...', 'info')
  
  // Load initial data
  await Promise.all([
    loadSystemStatus(),
    loadTelemetryData(),
    loadWeatherData()
  ])
  
  // Connect to WebSocket for real-time updates
  try {
    addLogEntry('Establishing WebSocket connection...', 'info')
    await connect()
    
    if (connected.value) {
      addLogEntry('WebSocket connected - subscribing to telemetry feeds', 'success')
      
      // Subscribe to telemetry topics with real data handling
      subscribe('telemetry.power', (data) => {
        if (data.battery) {
          batteryLevel.value = data.battery.percentage || 0
          batteryVoltage.value = (data.battery.voltage || 0).toFixed(1)
        }
        dataStreamText.value = `>>> POWER: ${batteryLevel.value.toFixed(1)}% | ${batteryVoltage.value}V`
      })
      
      subscribe('telemetry.navigation', (data) => {
        if (data.position && data.position.latitude && data.position.longitude) {
          gpsPosition.value = `${data.position.latitude.toFixed(6)}, ${data.position.longitude.toFixed(6)}`
          gpsStatus.value = 'SIGNAL ACQUIRED'
        } else {
          gpsPosition.value = 'NO SIGNAL'
          gpsStatus.value = 'SEARCHING...'
        }
        
        if (data.speed_mps !== undefined) {
          const newSpeed = data.speed_mps
          speedTrend.value = ((newSpeed - speed.value) / Math.max(speed.value, 0.1)) * 100
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
          systemStatus.value = data.safety_state === 'safe' ? 'Active' : 'Warning'
        }
      })
      
      subscribe('telemetry.weather', (data) => {
        if (data.temperature_c !== undefined) {
          temperature.value = data.temperature_c
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
        const { setCadence } = useWebSocket()
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
        loadSystemStatus(),
        loadTelemetryData(),
        loadWeatherData()
      ])
    }
  }, 2000) // 0.5Hz fallback rate
  
  // Cleanup on unmount
  onUnmounted(() => {
    clearInterval(refreshInterval)
    if (connected.value) {
      unsubscribe('telemetry.power')
      unsubscribe('telemetry.navigation')  
      unsubscribe('telemetry.motors')
      unsubscribe('telemetry.system')
      unsubscribe('telemetry.weather')
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
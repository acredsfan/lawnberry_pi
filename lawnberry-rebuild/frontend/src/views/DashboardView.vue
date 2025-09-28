<template>
  <div class="dashboard">
    <div class="page-header">
      <h1>Dashboard</h1>
      <p class="text-muted">System overview and real-time status</p>
    </div>

    <div class="row">
      <!-- System Status -->
      <div class="col-4">
        <StatusCard 
          title="System Status" 
          :description="`Uptime: ${uptime} | Connection: ${connectionStatus}`"
          :status="systemStatus"
        >
          <template #details>
            <div class="status-details">
              <div class="status-item">
                <span class="status-label">Overall Status:</span>
                <span class="status-value" :class="systemStatus">{{ systemStatus }}</span>
              </div>
              <div class="status-item">
                <span class="status-label">Connection:</span>
                <span class="status-value" :class="connectionStatus">{{ connectionStatus }}</span>
              </div>
            </div>
          </template>
        </StatusCard>
      </div>

      <!-- Quick Controls -->
      <div class="col-4">
        <ControlPanel title="Quick Controls" :status="currentMode === 'Idle' ? 'inactive' : 'active'">
          <div class="control-buttons">
            <button class="btn btn-success" :disabled="isLoading" @click="startSystem">
              Start System
            </button>
            <button class="btn btn-warning" :disabled="isLoading" @click="pauseSystem">
              Pause
            </button>
            <button class="btn btn-secondary" :disabled="isLoading" @click="stopSystem">
              Stop
            </button>
            <button class="btn btn-danger" :disabled="isLoading" @click="emergencyStop">
              Emergency Stop
            </button>
          </div>
        </ControlPanel>
      </div>

      <!-- Current Activity -->
      <div class="col-4">
        <MetricWidget 
          label="Current Activity"
          :value="progress"
          unit="%"
          icon="⚡"
          :show-progress="true"
          :max-value="100"
          variant="primary"
          progress-label="complete"
        />
      </div>
    </div>

    <div class="row">
      <!-- Live Telemetry -->
      <div class="col-3">
        <MetricWidget 
          label="GPS Position"
          :value="gpsPosition"
          icon="🌍"
          variant="info"
        />
      </div>
      
      <div class="col-3">
        <MetricWidget 
          label="Battery Level"
          :value="batteryLevel"
          unit="%"
          icon="🔋"
          :show-progress="true"
          :max-value="100"
          :variant="batteryLevel > 50 ? 'success' : batteryLevel > 20 ? 'warning' : 'danger'"
        />
      </div>
      
      <div class="col-3">
        <MetricWidget 
          label="Speed"
          :value="speed"
          unit="m/s"
          icon="🚀"
          :trend="speedTrend"
          variant="primary"
        />
      </div>
      
      <div class="col-3">
        <MetricWidget 
          label="Temperature"
          :value="temperature"
          unit="°C"
          icon="🌡️"
          :variant="temperature > 40 ? 'danger' : temperature > 30 ? 'warning' : 'success'"
        />
      </div>
    </div>

    <div class="row">
      <!-- Recent Events -->
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            <h3>Recent Events</h3>
          </div>
          <div class="card-body">
            <div class="events-list">
              <div
                v-for="event in recentEvents"
                :key="event.id"
                class="event-item"
                :class="event.level"
              >
                <div class="event-time">{{ formatTime(event.timestamp) }}</div>
                <div class="event-message">{{ event.message }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSystemStore } from '@/stores/system'
import { controlApi } from '@/composables/useApi'
import { useWebSocket } from '@/services/websocket'
import StatusCard from '@/components/StatusCard.vue'
import MetricWidget from '@/components/MetricWidget.vue'
import ControlPanel from '@/components/ControlPanel.vue'

const systemStore = useSystemStore()
const { connected, connecting, connect, subscribe, unsubscribe } = useWebSocket()

const isLoading = ref(false)
const currentMode = ref('Idle')
const progress = ref(0)
const uptime = ref('0h 0m')
const gpsPosition = ref('N/A')
const batteryLevel = ref(85.2)
const speed = ref(0.0)
const speedTrend = ref(5)
const temperature = ref(25.0)

// Live telemetry data
const telemetryData = ref({
  battery: { percentage: 85.2, voltage: 12.6 },
  position: { latitude: null, longitude: null },
  motor_status: 'idle',
  safety_state: 'safe',
  weather: { temperature_c: 25.0, humidity_percent: 60 },
  system: { cpu_usage_percent: 30, memory_usage_percent: 45 },
  lastUpdate: new Date()
})

const recentEvents = ref([
  { id: 1, timestamp: new Date(), message: 'System started successfully', level: 'info' },
  { id: 2, timestamp: new Date(Date.now() - 60000), message: 'GPS signal acquired', level: 'success' },
  { id: 3, timestamp: new Date(Date.now() - 120000), message: 'Sensors initialized', level: 'info' },
])

const systemStatus = computed(() => systemStore.status)
const connectionStatus = computed(() => systemStore.connectionStatus)

const startSystem = async () => {
  try {
    isLoading.value = true
    await controlApi.start()
    currentMode.value = 'Running'
  } catch (error) {
    console.error('Failed to start system:', error)
  } finally {
    isLoading.value = false
  }
}

const pauseSystem = async () => {
  try {
    isLoading.value = true
    await controlApi.pause()
    currentMode.value = 'Paused'
  } catch (error) {
    console.error('Failed to pause system:', error)
  } finally {
    isLoading.value = false
  }
}

const stopSystem = async () => {
  try {
    isLoading.value = true
    await controlApi.stop()
    currentMode.value = 'Stopped'
  } catch (error) {
    console.error('Failed to stop system:', error)
  } finally {
    isLoading.value = false
  }
}

const emergencyStop = async () => {
  try {
    isLoading.value = true
    await controlApi.emergencyStop()
    currentMode.value = 'Emergency Stop'
  } catch (error) {
    console.error('Failed to emergency stop:', error)
  } finally {
    isLoading.value = false
  }
}

const formatTime = (timestamp: Date) => {
  return timestamp.toLocaleTimeString()
}

onMounted(async () => {
  // Connect to WebSocket for live telemetry
  await connect()
  
  // Subscribe to telemetry topics
  subscribe('telemetry.power', (data) => {
    if (data.battery) {
      telemetryData.value.battery = data.battery
      batteryLevel.value = data.battery.percentage || 0
    }
    telemetryData.value.lastUpdate = new Date()
  })
  
  subscribe('telemetry.navigation', (data) => {
    if (data.position) {
      telemetryData.value.position = data.position
      if (data.position.latitude && data.position.longitude) {
        gpsPosition.value = `${data.position.latitude.toFixed(6)}, ${data.position.longitude.toFixed(6)}`
      }
    }
    telemetryData.value.lastUpdate = new Date()
  })
  
  subscribe('telemetry.motors', (data) => {
    if (data.motor_status) {
      telemetryData.value.motor_status = data.motor_status
      currentMode.value = data.motor_status === 'idle' ? 'Idle' : 'Running'
    }
    telemetryData.value.lastUpdate = new Date()
  })
  
  subscribe('telemetry.system', (data) => {
    if (data.safety_state) {
      telemetryData.value.safety_state = data.safety_state
    }
    if (data.uptime_seconds) {
      const uptimeSeconds = data.uptime_seconds
      const hours = Math.floor(uptimeSeconds / 3600)
      const minutes = Math.floor((uptimeSeconds % 3600) / 60)
      uptime.value = `${hours}h ${minutes}m`
    }
    telemetryData.value.lastUpdate = new Date()
  })
  
  subscribe('telemetry.weather', (data) => {
    if (data.temperature_c) {
      telemetryData.value.weather.temperature_c = data.temperature_c
      temperature.value = data.temperature_c
    }
    if (data.humidity_percent) {
      telemetryData.value.weather.humidity_percent = data.humidity_percent
    }
    telemetryData.value.lastUpdate = new Date()
  })
  
  subscribe('system.performance', (data) => {
    if (data.cpu_usage_percent) {
      telemetryData.value.system.cpu_usage_percent = data.cpu_usage_percent
    }
    if (data.memory_usage_percent) {
      telemetryData.value.system.memory_usage_percent = data.memory_usage_percent
    }
    telemetryData.value.lastUpdate = new Date()
  })
  
  subscribe('jobs.progress', (data) => {
    if (data.progress_percent !== undefined) {
      progress.value = data.progress_percent
    }
    if (data.current_job) {
      currentMode.value = data.status === 'running' ? `Running: ${data.current_job}` : 'Idle'
    }
    telemetryData.value.lastUpdate = new Date()
  })
})

onUnmounted(() => {
  // Cleanup subscriptions
  unsubscribe('telemetry.power')
  unsubscribe('telemetry.navigation')
  unsubscribe('telemetry.motors')
  unsubscribe('telemetry.system')
  unsubscribe('telemetry.weather')
  unsubscribe('system.performance')
  unsubscribe('jobs.progress')
})
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
}

.status-item,
.activity-item,
.telemetry-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.status-label,
.activity-label,
.telemetry-label {
  font-weight: 500;
  color: #6c757d;
}

.status-value {
  font-weight: 600;
  text-transform: capitalize;
}

.status-value.active,
.status-value.connected {
  color: #27ae60;
}

.status-value.warning {
  color: #f39c12;
}

.status-value.error,
.status-value.disconnected {
  color: #e74c3c;
}

.control-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background-color: #e9ecef;
  border-radius: 4px;
  margin: 0 1rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: #3498db;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.telemetry-grid {
  display: grid;
  gap: 0.75rem;
}

.events-list {
  max-height: 200px;
  overflow-y: auto;
}

.event-item {
  padding: 0.5rem;
  border-left: 3px solid #dee2e6;
  margin-bottom: 0.5rem;
  border-radius: 0 4px 4px 0;
}

.event-item.info {
  border-left-color: #3498db;
  background-color: rgba(52, 152, 219, 0.05);
}

.event-item.success {
  border-left-color: #27ae60;
  background-color: rgba(39, 174, 96, 0.05);
}

.event-item.warning {
  border-left-color: #f39c12;
  background-color: rgba(243, 156, 18, 0.05);
}

.event-item.error {
  border-left-color: #e74c3c;
  background-color: rgba(231, 76, 60, 0.05);
}

.event-time {
  font-size: 0.75rem;
  color: #6c757d;
  margin-bottom: 0.25rem;
}

.event-message {
  font-size: 0.875rem;
}

/* Mobile-first responsive improvements */
.control-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
}

.status-details {
  display: grid;
  gap: 0.5rem;
}

/* Tablet adjustments */
@media (min-width: 481px) and (max-width: 768px) {
  .control-buttons {
    grid-template-columns: 1fr 1fr;
  }
  
  .dashboard .row .col-4 {
    margin-bottom: 1rem;
  }
}

/* Mobile adjustments */
@media (max-width: 480px) {
  .control-buttons {
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
  
  .control-buttons .btn {
    padding: 1rem;
    font-size: 1rem;
    font-weight: 600;
  }
  
  .telemetry-item,
  .status-item,
  .activity-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.25rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid #e9ecef;
  }
  
  .telemetry-item:last-child,
  .status-item:last-child,
  .activity-item:last-child {
    border-bottom: none;
  }
  
  .progress-bar {
    margin: 0.5rem 0;
    width: 100%;
  }
  
  .events-list {
    max-height: 300px;
  }
  
  .event-item {
    padding: 0.75rem;
    margin-bottom: 0.75rem;
  }
  
  .event-time {
    font-size: 0.875rem;
  }
  
  .event-message {
    font-size: 1rem;
    line-height: 1.4;
  }
}
</style>
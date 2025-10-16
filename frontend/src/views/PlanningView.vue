<template>
  <div class="planning-view">
    <div class="page-header">
      <h1>Mow Planning</h1>
      <p class="text-muted">Schedule mowing jobs, manage zones, and optimize operations</p>
    </div>

    <!-- Quick Start Actions -->
    <div class="quick-actions">
      <button class="btn btn-primary quick-btn" @click="startQuickMow">
        ⚡ Quick Mow
      </button>
      <button class="btn btn-success quick-btn" @click="openScheduleModal">
        📅 Schedule Job
      </button>
      <button class="btn btn-info quick-btn" @click="activeTab = 'zones'">
        🗺️ Manage Zones
      </button>
    </div>

    <!-- Planning Tabs -->
    <div class="planning-tabs">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        class="tab-button"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Current Jobs -->
    <div v-if="activeTab === 'current'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Current & Queued Jobs</h3>
          <button class="btn btn-sm btn-secondary" @click="refreshJobs">
            🔄 Refresh
          </button>
        </div>
        <div class="card-body">
          <div v-if="jobs.length === 0" class="empty-state">
            <p>No active or queued jobs</p>
            <button class="btn btn-primary" @click="openScheduleModal">
              Schedule First Job
            </button>
          </div>
          
          <div v-else class="jobs-list">
            <div 
              v-for="job in jobs" 
              :key="job.id"
              class="job-item"
              :class="`status-${job.status}`"
            >
              <div class="job-header">
                <div class="job-title">
                  <h4>{{ job.name }}</h4>
                  <span class="status-badge" :class="`status-${job.status}`">
                    {{ formatJobStatus(job.status) }}
                  </span>
                </div>
                <div class="job-actions">
                  <button 
                    v-if="job.status === 'scheduled'"
                    class="btn btn-xs btn-success"
                    @click="startJob(job)"
                  >
                    ▶️ Start
                  </button>
                  <button 
                    v-if="job.status === 'running'"
                    class="btn btn-xs btn-warning"
                    @click="pauseJob(job)"
                  >
                    ⏸️ Pause
                  </button>
                  <button 
                    v-if="job.status === 'paused'"
                    class="btn btn-xs btn-success"
                    @click="resumeJob(job)"
                  >
                    ▶️ Resume
                  </button>
                  <button 
                    class="btn btn-xs btn-danger"
                    :disabled="job.status === 'completed'"
                    @click="cancelJob(job)"
                  >
                    ❌ Cancel
                  </button>
                </div>
              </div>
              
              <div class="job-details">
                <div class="job-info">
                  <span>Zones: {{ job.zones.join(', ') }}</span>
                  <span>Pattern: {{ job.pattern }}</span>
                  <span v-if="job.scheduled_start">Start: {{ formatDateTime(job.scheduled_start) }}</span>
                </div>
                
                <div v-if="job.status === 'running'" class="job-progress">
                  <div class="progress-bar">
                    <div class="progress-fill" :style="{ width: `${job.progress}%` }" />
                  </div>
                  <span class="progress-text">{{ job.progress }}% complete</span>
                  <span v-if="job.estimated_remaining" class="time-remaining">
                    ~{{ job.estimated_remaining }} min remaining
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Job History -->
      <div class="card">
        <div class="card-header">
          <h3>Recent Job History</h3>
        </div>
        <div class="card-body">
          <div class="history-list">
            <div 
              v-for="job in completedJobs" 
              :key="job.id"
              class="history-item"
            >
              <div class="history-header">
                <span class="job-name">{{ job.name }}</span>
                <span class="completion-time">{{ formatDateTime(job.completed_at) }}</span>
              </div>
              <div class="history-details">
                <span>Duration: {{ job.actual_duration }} min</span>
                <span>Area: {{ formatArea(job.area_covered) }} {{ areaUnit }}</span>
                <span class="success-indicator">✅ Completed</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Scheduling -->
    <div v-if="activeTab === 'schedule'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Recurring Schedules</h3>
          <button class="btn btn-sm btn-primary" @click="openScheduleModal">
            ➕ Add Schedule
          </button>
        </div>
        <div class="card-body">
          <div v-if="schedules.length === 0" class="empty-state">
            <p>No recurring schedules configured</p>
          </div>
          
          <div v-else class="schedules-list">
            <div 
              v-for="schedule in schedules" 
              :key="schedule.id"
              class="schedule-item"
            >
              <div class="schedule-header">
                <div class="schedule-info">
                  <h4>{{ schedule.name }}</h4>
                  <span class="schedule-frequency">{{ formatFrequency(schedule.frequency) }}</span>
                </div>
                <div class="schedule-actions">
                  <button 
                    class="btn btn-xs"
                    :class="schedule.enabled ? 'btn-warning' : 'btn-success'"
                    @click="toggleSchedule(schedule)"
                  >
                    {{ schedule.enabled ? '⏸️ Disable' : '▶️ Enable' }}
                  </button>
                  <button class="btn btn-xs btn-secondary" @click="editSchedule(schedule)">
                    ✏️ Edit
                  </button>
                  <button class="btn btn-xs btn-danger" @click="deleteSchedule(schedule)">
                    🗑️ Delete
                  </button>
                </div>
              </div>
              
              <div class="schedule-details">
                <span>Zones: {{ schedule.zones.join(', ') }}</span>
                <span>Pattern: {{ schedule.pattern }}</span>
                <span>Next run: {{ formatDateTime(schedule.next_run) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Weather & Conditions -->
      <div class="card">
        <div class="card-header">
          <h3>Current Conditions</h3>
        </div>
        <div class="card-body">
          <div class="conditions-grid">
            <div class="condition-item">
              <div class="condition-label">Weather</div>
              <div class="condition-value" :class="weatherClass">
                {{ currentWeather.condition || 'Loading...' }}
              </div>
              <div class="condition-detail">
                {{ weatherTemperatureDisplay }}{{ temperatureUnit }}, {{ currentWeather.humidity_percent }}% humidity
              </div>
            </div>
            
            <div class="condition-item">
              <div class="condition-label">Mowing Recommendation</div>
              <div class="condition-value" :class="recommendationClass">
                {{ recommendation.advice }}
              </div>
              <div class="condition-detail">{{ recommendation.reason }}</div>
            </div>
            
            <div class="condition-item">
              <div class="condition-label">Ground Conditions</div>
              <div class="condition-value" :class="groundClass">
                {{ groundCondition }}
              </div>
              <div class="condition-detail">Last rain: {{ lastRain }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Zone Management -->
    <div v-if="activeTab === 'zones'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Mowing Zones</h3>
          <button class="btn btn-sm btn-primary" @click="openZoneModal">
            ➕ Add Zone
          </button>
        </div>
        <div class="card-body">
          <div class="zones-grid">
            <div 
              v-for="zone in zones" 
              :key="zone.id"
              class="zone-card"
              :class="{ active: selectedZone?.id === zone.id }"
              @click="selectZone(zone)"
            >
              <div class="zone-header">
                <h4>{{ zone.name }}</h4>
                <span class="zone-priority" :class="`priority-${zone.priority}`">
                  {{ formatPriority(zone.priority) }}
                </span>
              </div>
              
              <div class="zone-stats">
                <div class="stat">
                  <span class="stat-label">Area</span>
                  <span class="stat-value">{{ formatArea(zone.area_m2) }} {{ areaUnit }}</span>
                </div>
                <div class="stat">
                  <span class="stat-label">Height</span>
                  <span class="stat-value">{{ formatCuttingHeight(zone.cutting_height) }} {{ cuttingHeightUnit }}</span>
                </div>
                <div class="stat">
                  <span class="stat-label">Last Cut</span>
                  <span class="stat-value">{{ formatRelativeTime(zone.last_mowed) }}</span>
                </div>
              </div>
              
              <div class="zone-actions">
                <button class="btn btn-xs btn-success" @click.stop="mowZone(zone)">
                  🌱 Mow Now
                </button>
                <button class="btn btn-xs btn-secondary" @click.stop="editZone(zone)">
                  ✏️ Edit
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Patterns -->
    <div v-if="activeTab === 'patterns'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Mowing Patterns</h3>
        </div>
        <div class="card-body">
          <div class="patterns-grid">
            <div 
              v-for="pattern in patterns" 
              :key="pattern.id"
              class="pattern-card"
              :class="{ selected: selectedPattern === pattern.id }"
              @click="selectedPattern = pattern.id"
            >
              <div class="pattern-preview">
                <div class="pattern-visual" :class="`pattern-${pattern.id}`" />
              </div>
              <div class="pattern-info">
                <h4>{{ pattern.name }}</h4>
                <p>{{ pattern.description }}</p>
                <div class="pattern-stats">
                  <span>Efficiency: {{ pattern.efficiency }}%</span>
                  <span>Coverage: {{ pattern.coverage }}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Schedule Job Modal -->
    <div v-if="showScheduleModal" class="modal-overlay" @click="closeScheduleModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ editingSchedule ? 'Edit Schedule' : 'Schedule Mowing Job' }}</h3>
          <button class="btn btn-sm btn-secondary" @click="closeScheduleModal">✖️</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>Job Name</label>
            <input v-model="scheduleForm.name" type="text" class="form-control">
          </div>
          
          <div class="form-group">
            <label>Zones to Mow</label>
            <div class="zone-checkboxes">
              <label v-for="zone in zones" :key="zone.id" class="checkbox-label">
                <input 
                  v-model="scheduleForm.zones" 
                  type="checkbox"
                  :value="zone.id"
                >
                {{ zone.name }}
              </label>
            </div>
          </div>
          
          <div class="form-group">
            <label>Mowing Pattern</label>
            <select v-model="scheduleForm.pattern" class="form-control">
              <option v-for="pattern in patterns" :key="pattern.id" :value="pattern.id">
                {{ pattern.name }}
              </option>
            </select>
          </div>
          
          <div class="form-group">
            <label>Schedule Type</label>
            <select v-model="scheduleForm.type" class="form-control">
              <option value="once">One-time job</option>
              <option value="recurring">Recurring schedule</option>
            </select>
          </div>
          
          <div v-if="scheduleForm.type === 'once'" class="form-group">
            <label>Start Time</label>
            <input 
              v-model="scheduleForm.startTime" 
              type="datetime-local" 
              class="form-control"
            >
          </div>
          
          <div v-if="scheduleForm.type === 'recurring'" class="recurring-options">
            <div class="form-group">
              <label>Frequency</label>
              <select v-model="scheduleForm.frequency" class="form-control">
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="biweekly">Every 2 weeks</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
            
            <div class="form-group">
              <label>Time of Day</label>
              <input 
                v-model="scheduleForm.timeOfDay" 
                type="time" 
                class="form-control"
              >
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeScheduleModal">Cancel</button>
          <button class="btn btn-primary" @click="saveSchedule">
            {{ editingSchedule ? 'Update' : 'Schedule' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessage" class="alert" :class="statusSuccess ? 'alert-success' : 'alert-danger'">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useApiService } from '@/services/api'
import { useWebSocket } from '@/services/websocket'
import { usePreferencesStore } from '@/stores/preferences'

const api = useApiService()
const { connected, connect, subscribe, unsubscribe } = useWebSocket()
const preferences = usePreferencesStore()

preferences.ensureInitialized()
const { unitSystem } = storeToRefs(preferences)

// State
const activeTab = ref('current')
const showScheduleModal = ref(false)
const editingSchedule = ref<any>(null)
const selectedZone = ref<any>(null)
const selectedPattern = ref('parallel')
const statusMessage = ref('')
const statusSuccess = ref(false)

// Tabs
const tabs = [
  { id: 'current', label: 'Current Jobs' },
  { id: 'schedule', label: 'Scheduling' },
  { id: 'zones', label: 'Zones' },
  { id: 'patterns', label: 'Patterns' }
]

// Data
const jobs = ref([
  {
    id: 1,
    name: 'Front Lawn Weekly',
    status: 'running',
    zones: ['Front Lawn', 'Side Lawn'],
    pattern: 'parallel',
    progress: 45,
    estimated_remaining: 25,
    scheduled_start: '2024-09-28T10:00:00'
  },
  {
    id: 2,
    name: 'Back Lawn Maintenance',
    status: 'scheduled',
    zones: ['Back Lawn'],
    pattern: 'spiral',
    progress: 0,
    estimated_remaining: null,
    scheduled_start: '2024-09-28T14:00:00'
  }
])

const completedJobs = ref([
  {
    id: 3,
    name: 'Full Property Mow',
    completed_at: '2024-09-27T16:30:00',
    actual_duration: 180,
    area_covered: 450
  },
  {
    id: 4,
    name: 'Front Lawn Touch-up',
    completed_at: '2024-09-26T11:15:00',
    actual_duration: 45,
    area_covered: 150
  }
])

const schedules = ref([
  {
    id: 1,
    name: 'Weekly Full Property',
    frequency: 'weekly',
    zones: ['Front Lawn', 'Back Lawn', 'Side Lawn'],
    pattern: 'parallel',
    enabled: true,
    next_run: '2024-09-30T10:00:00'
  },
  {
    id: 2,
    name: 'Bi-weekly Edge Trim',
    frequency: 'biweekly',
    zones: ['Perimeter'],
    pattern: 'edge',
    enabled: false,
    next_run: '2024-10-05T09:00:00'
  }
])

const zones = ref([
  {
    id: 'front_lawn',
    name: 'Front Lawn',
    area_m2: 200,
    cutting_height: 35,
    priority: 'high',
    last_mowed: '2024-09-26T10:00:00'
  },
  {
    id: 'back_garden',
    name: 'Back Lawn',
    area_m2: 150,
    cutting_height: 40,
    priority: 'medium',
    last_mowed: '2024-09-25T14:00:00'
  },
  {
    id: 'side_garden',
    name: 'Side Lawn',
    area_m2: 75,
    cutting_height: 30,
    priority: 'low',
    last_mowed: '2024-09-24T16:00:00'
  }
])

const patterns = ref([
  {
    id: 'parallel',
    name: 'Parallel Lines',
    description: 'Straight parallel lines across the area',
    efficiency: 95,
    coverage: 98
  },
  {
    id: 'spiral',
    name: 'Spiral',
    description: 'Spiral pattern from outside to center',
    efficiency: 85,
    coverage: 95
  },
  {
    id: 'random',
    name: 'Random',
    description: 'Random movement pattern',
    efficiency: 70,
    coverage: 92
  },
  {
    id: 'edge',
    name: 'Edge First',
    description: 'Cut edges first, then fill interior',
    efficiency: 90,
    coverage: 99
  }
])

const currentWeather = ref({
  temperature_c: 22,
  humidity_percent: 65,
  condition: 'Partly Cloudy'
})

const temperatureUnit = computed(() => (unitSystem.value === 'imperial' ? '°F' : '°C'))
const weatherTemperatureDisplay = computed(() => {
  const raw = Number(currentWeather.value.temperature_c)
  if (!Number.isFinite(raw)) {
    return '--'
  }
  const converted = unitSystem.value === 'imperial' ? (raw * 9) / 5 + 32 : raw
  const formatter = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  return formatter.format(converted)
})

const areaUnit = computed(() => (unitSystem.value === 'imperial' ? 'ft²' : 'm²'))
const cuttingHeightUnit = computed(() => (unitSystem.value === 'imperial' ? 'in' : 'mm'))

const formatArea = (value: unknown): string => {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) {
    return 'N/A'
  }
  const converted = unitSystem.value === 'imperial' ? numeric * 10.7639104167 : numeric
  const formatter = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: converted >= 100 ? 0 : 1,
    maximumFractionDigits: converted >= 100 ? 0 : 1,
  })
  return formatter.format(converted)
}

const formatCuttingHeight = (value: unknown): string => {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) {
    return 'N/A'
  }
  if (unitSystem.value === 'imperial') {
    const inches = numeric * 0.0393700787
    const formatter = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    })
    return formatter.format(inches)
  }
  const formatter = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
  return formatter.format(numeric)
}

const recommendation = ref({
  advice: 'Proceed',
  reason: 'Good weather conditions for mowing'
})

const scheduleForm = ref({
  name: '',
  zones: [],
  pattern: 'parallel',
  type: 'once',
  startTime: '',
  frequency: 'weekly',
  timeOfDay: '10:00'
})

// Computed
const weatherClass = computed(() => {
  const condition = currentWeather.value.condition?.toLowerCase()
  if (condition?.includes('rain') || condition?.includes('storm')) return 'condition-bad'
  if (condition?.includes('cloud') || condition?.includes('overcast')) return 'condition-warn'
  return 'condition-good'
})

const recommendationClass = computed(() => {
  const advice = recommendation.value.advice?.toLowerCase()
  if (advice === 'proceed') return 'condition-good'
  if (advice === 'caution') return 'condition-warn'
  return 'condition-bad'
})

const groundClass = computed(() => 'condition-good')
const groundCondition = computed(() => 'Dry')
const lastRain = computed(() => '2 days ago')

// Methods
async function startQuickMow() {
  try {
    await api.post('/api/v2/mow/jobs', {
      name: 'Quick Mow',
      zones: ['front_lawn'],
      pattern: 'parallel',
      start_immediately: true
    })
    showStatus('Quick mow started successfully!', true)
    await refreshJobs()
  } catch (error) {
    showStatus('Failed to start quick mow', false)
  }
}

function openScheduleModal() {
  editingSchedule.value = null
  scheduleForm.value = {
    name: '',
    zones: [],
    pattern: 'parallel',
    type: 'once',
    startTime: '',
    frequency: 'weekly',
    timeOfDay: '10:00'
  }
  showScheduleModal.value = true
}

function closeScheduleModal() {
  showScheduleModal.value = false
  editingSchedule.value = null
}

async function saveSchedule() {
  try {
    const endpoint = editingSchedule.value 
      ? `/api/v2/schedules/${editingSchedule.value.id}`
      : '/api/v2/schedules'
    
    const method = editingSchedule.value ? 'put' : 'post'
    
    await api[method](endpoint, scheduleForm.value)
    
    showStatus(
      editingSchedule.value ? 'Schedule updated!' : 'Schedule created!', 
      true
    )
    
    closeScheduleModal()
    await refreshSchedules()
  } catch (error) {
    showStatus('Failed to save schedule', false)
  }
}

async function refreshJobs() {
  try {
    const response = await api.get('/api/v2/mow/jobs')
    jobs.value = response.data.active || []
  } catch (error) {
    console.error('Failed to refresh jobs:', error)
  }
}

async function refreshSchedules() {
  try {
    const response = await api.get('/api/v2/schedules')
    schedules.value = response.data || []
  } catch (error) {
    console.error('Failed to refresh schedules:', error)
  }
}

async function startJob(job: any) {
  try {
    await api.post(`/api/v2/mow/jobs/${job.id}/start`)
    job.status = 'running'
    showStatus('Job started!', true)
  } catch (error) {
    showStatus('Failed to start job', false)
  }
}

async function pauseJob(job: any) {
  try {
    await api.post(`/api/v2/mow/jobs/${job.id}/pause`)
    job.status = 'paused'
    showStatus('Job paused', true)
  } catch (error) {
    showStatus('Failed to pause job', false)
  }
}

async function resumeJob(job: any) {
  try {
    await api.post(`/api/v2/mow/jobs/${job.id}/resume`)
    job.status = 'running'
    showStatus('Job resumed!', true)
  } catch (error) {
    showStatus('Failed to resume job', false)
  }
}

async function cancelJob(job: any) {
  if (!confirm(`Cancel job "${job.name}"?`)) return
  
  try {
    await api.delete(`/api/v2/mow/jobs/${job.id}`)
    const index = jobs.value.findIndex(j => j.id === job.id)
    if (index > -1) jobs.value.splice(index, 1)
    showStatus('Job cancelled', true)
  } catch (error) {
    showStatus('Failed to cancel job', false)
  }
}

async function toggleSchedule(schedule: any) {
  try {
    await api.put(`/api/v2/schedules/${schedule.id}`, {
      ...schedule,
      enabled: !schedule.enabled
    })
    schedule.enabled = !schedule.enabled
    showStatus(
      schedule.enabled ? 'Schedule enabled' : 'Schedule disabled', 
      true
    )
  } catch (error) {
    showStatus('Failed to toggle schedule', false)
  }
}

function editSchedule(schedule: any) {
  editingSchedule.value = schedule
  scheduleForm.value = { ...schedule }
  showScheduleModal.value = true
}

async function deleteSchedule(schedule: any) {
  if (!confirm(`Delete schedule "${schedule.name}"?`)) return
  
  try {
    await api.delete(`/api/v2/schedules/${schedule.id}`)
    const index = schedules.value.findIndex(s => s.id === schedule.id)
    if (index > -1) schedules.value.splice(index, 1)
    showStatus('Schedule deleted', true)
  } catch (error) {
    showStatus('Failed to delete schedule', false)
  }
}

function selectZone(zone: any) {
  selectedZone.value = selectedZone.value?.id === zone.id ? null : zone
}

async function mowZone(zone: any) {
  try {
    await api.post('/api/v2/mow/jobs', {
      name: `${zone.name} - Quick Mow`,
      zones: [zone.id],
      pattern: 'parallel',
      start_immediately: true
    })
    showStatus(`Started mowing ${zone.name}`, true)
    await refreshJobs()
  } catch (error) {
    showStatus(`Failed to start mowing ${zone.name}`, false)
  }
}

function openZoneModal() {
  // Placeholder for zone creation modal
  showStatus('Zone management coming soon', true)
}

function editZone(zone: any) {
  // Placeholder for zone editing
  showStatus('Zone editing coming soon', true)
}

function formatJobStatus(status: string): string {
  const statusMap = {
    scheduled: 'Scheduled',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    cancelled: 'Cancelled',
    failed: 'Failed'
  }
  return statusMap[status as keyof typeof statusMap] || status
}

function formatFrequency(frequency: string): string {
  const freqMap = {
    daily: 'Daily',
    weekly: 'Weekly',
    biweekly: 'Every 2 weeks',
    monthly: 'Monthly'
  }
  return freqMap[frequency as keyof typeof freqMap] || frequency
}

function formatPriority(priority: string): string {
  return priority.charAt(0).toUpperCase() + priority.slice(1)
}

function formatDateTime(dateString: string): string {
  try {
    return new Date(dateString).toLocaleString()
  } catch {
    return dateString
  }
}

function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    
    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays} days ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
    return `${Math.floor(diffDays / 30)} months ago`
  } catch {
    return 'Unknown'
  }
}

function showStatus(message: string, success: boolean) {
  statusMessage.value = message
  statusSuccess.value = success
  setTimeout(() => {
    statusMessage.value = ''
  }, 3000)
}

onMounted(async () => {
  await connect()
  
  // Subscribe to job progress updates
  subscribe('jobs.progress', (data) => {
    const job = jobs.value.find(j => j.id === data.job_id)
    if (job) {
      job.progress = data.progress_percent
      job.estimated_remaining = data.remaining_time_min
    }
  })
  
  // Subscribe to weather updates
  subscribe('telemetry.weather', (data) => {
    currentWeather.value = {
      temperature_c: data.temperature_c ?? currentWeather.value.temperature_c,
      humidity_percent: data.humidity_percent || currentWeather.value.humidity_percent,
      condition: data.condition || currentWeather.value.condition
    }
  })
  
  await refreshJobs()
  await refreshSchedules()
})
</script>

<style scoped>
.planning-view {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
}

.quick-actions {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.quick-btn {
  padding: 1rem 1.5rem;
  font-size: 1.1rem;
  border-radius: 8px;
}

.planning-tabs {
  display: flex;
  border-bottom: 2px solid var(--primary-dark);
  margin-bottom: 2rem;
  overflow-x: auto;
}

.tab-button {
  background: none;
  border: none;
  padding: 1rem 2rem;
  color: var(--text-color);
  font-weight: 500;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.tab-button:hover {
  background-color: var(--primary-dark);
  color: var(--primary-light);
}

.tab-button.active {
  border-bottom-color: var(--accent-green);
  color: var(--accent-green);
  background-color: var(--primary-dark);
}

.tab-content {
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.card {
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  margin-bottom: 2rem;
}

.card-header {
  background: var(--primary-dark);
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--primary-light);
  border-radius: 8px 8px 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  color: var(--accent-green);
  font-size: 1.25rem;
}

.card-body {
  padding: 1.5rem;
}

.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-muted);
}

.jobs-list, .schedules-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.job-item, .schedule-item {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1rem;
  transition: all 0.3s ease;
}

.job-item:hover, .schedule-item:hover {
  border-color: var(--accent-green);
}

.job-header, .schedule-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.job-title, .schedule-info {
  flex: 1;
}

.job-title h4, .schedule-info h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-color);
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-scheduled {
  background: rgba(0, 123, 255, 0.2);
  color: #007bff;
  border: 1px solid #007bff;
}

.status-running {
  background: rgba(0, 255, 146, 0.2);
  color: var(--accent-green);
  border: 1px solid var(--accent-green);
}

.status-paused {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
  border: 1px solid #ffc107;
}

.status-completed {
  background: rgba(40, 167, 69, 0.2);
  color: #28a745;
  border: 1px solid #28a745;
}

.job-actions, .schedule-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.job-details, .schedule-details {
  color: var(--text-muted);
  font-size: 0.875rem;
}

.job-info, .schedule-details {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.job-progress {
  margin-top: 1rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--primary-light);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: var(--accent-green);
  transition: width 0.3s ease;
}

.progress-text, .time-remaining {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-right: 1rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.history-item {
  background: var(--primary-dark);
  padding: 0.75rem;
  border-radius: 4px;
  border-left: 3px solid var(--accent-green);
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.job-name {
  font-weight: 500;
  color: var(--text-color);
}

.completion-time {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.history-details {
  display: flex;
  gap: 1rem;
  font-size: 0.875rem;
  color: var(--text-muted);
  flex-wrap: wrap;
}

.success-indicator {
  color: var(--accent-green);
}

.schedule-frequency {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.conditions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.condition-item {
  background: var(--primary-dark);
  padding: 1rem;
  border-radius: 8px;
  text-align: center;
}

.condition-label {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.condition-value {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.condition-good {
  color: var(--accent-green);
}

.condition-warn {
  color: #ffc107;
}

.condition-bad {
  color: #ff4343;
}

.condition-detail {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.zones-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}

.zone-card {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.zone-card:hover {
  border-color: var(--accent-green);
  transform: translateY(-2px);
}

.zone-card.active {
  border-color: var(--accent-green);
  background: rgba(0, 255, 146, 0.1);
}

.zone-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.zone-header h4 {
  margin: 0;
  color: var(--text-color);
}

.zone-priority {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.priority-high {
  background: rgba(255, 67, 67, 0.2);
  color: #ff4343;
}

.priority-medium {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
}

.priority-low {
  background: rgba(0, 255, 146, 0.2);
  color: var(--accent-green);
}

.zone-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.stat {
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.25rem;
}

.stat-value {
  font-weight: 600;
  color: var(--text-color);
}

.zone-actions {
  display: flex;
  gap: 0.5rem;
}

.patterns-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.pattern-card {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.pattern-card:hover {
  border-color: var(--accent-green);
}

.pattern-card.selected {
  border-color: var(--accent-green);
  background: rgba(0, 255, 146, 0.1);
}

.pattern-preview {
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
  background: var(--secondary-dark);
  border-radius: 4px;
}

.pattern-visual {
  width: 60px;
  height: 60px;
  border-radius: 4px;
}

.pattern-parallel {
  background: linear-gradient(to right, var(--accent-green) 0%, transparent 0%, transparent 20%, var(--accent-green) 20%, var(--accent-green) 40%, transparent 40%, transparent 60%, var(--accent-green) 60%, var(--accent-green) 80%, transparent 80%);
}

.pattern-spiral {
  background: radial-gradient(circle, transparent 30%, var(--accent-green) 30%, var(--accent-green) 40%, transparent 40%);
  border: 2px solid var(--accent-green);
  border-radius: 50%;
}

.pattern-random {
  background: var(--accent-green);
  clip-path: polygon(20% 0%, 80% 0%, 100% 20%, 80% 40%, 100% 60%, 75% 100%, 25% 100%, 0% 80%, 20% 60%, 0% 40%);
}

.pattern-edge {
  border: 3px solid var(--accent-green);
  position: relative;
}

.pattern-edge::after {
  content: '';
  position: absolute;
  top: 20%;
  left: 20%;
  right: 20%;
  bottom: 20%;
  background: var(--accent-green);
  opacity: 0.5;
}

.pattern-info h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-color);
}

.pattern-info p {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: 1rem;
}

.pattern-stats {
  display: flex;
  gap: 1rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-primary {
  background: var(--accent-green);
  color: var(--primary-dark);
}

.btn-secondary {
  background: var(--primary-light);
  color: var(--text-color);
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-warning {
  background: #ffc107;
  color: #000;
}

.btn-info {
  background: #17a2b8;
  color: white;
}

.btn-danger {
  background: #ff4343;
  color: white;
}

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
}

.btn-xs {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--primary-light);
}

.modal-header h3 {
  margin: 0;
  color: var(--accent-green);
}

.modal-body {
  padding: 1.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid var(--primary-light);
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-color);
  font-weight: 500;
}

.form-control {
  width: 100%;
  padding: 0.75rem;
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  color: var(--text-color);
  font-size: 1rem;
}

.form-control:focus {
  outline: none;
  border-color: var(--accent-green);
  box-shadow: 0 0 0 2px rgba(0, 255, 146, 0.2);
}

.zone-checkboxes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--primary-dark);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.checkbox-label:hover {
  background: var(--secondary-dark);
}

.recurring-options {
  margin-left: 1rem;
  padding-left: 1rem;
  border-left: 3px solid var(--accent-green);
}

.alert {
  padding: 1rem;
  border-radius: 4px;
  margin-top: 2rem;
}

.alert-success {
  background: rgba(0, 255, 146, 0.1);
  border: 1px solid var(--accent-green);
  color: var(--accent-green);
}

.alert-danger {
  background: rgba(255, 67, 67, 0.1);
  border: 1px solid #ff4343;
  color: #ff4343;
}

@media (max-width: 768px) {
  .quick-actions {
    flex-direction: column;
  }
  
  .planning-tabs {
    flex-direction: column;
  }
  
  .tab-button {
    padding: 0.75rem 1rem;
    text-align: left;
  }
  
  .job-header, .schedule-header {
    flex-direction: column;
    gap: 1rem;
    align-items: stretch;
  }
  
  .job-info, .schedule-details {
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .conditions-grid {
    grid-template-columns: 1fr;
  }
  
  .zones-grid, .patterns-grid {
    grid-template-columns: 1fr;
  }
  
  .zone-checkboxes {
    grid-template-columns: 1fr;
  }
}
</style>
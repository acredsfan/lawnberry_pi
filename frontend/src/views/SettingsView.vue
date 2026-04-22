<template>
  <div class="settings-view">
    <div class="page-header">
      <h1>Settings</h1>
      <p class="text-muted">System configuration and preferences</p>
    </div>
    
    <!-- Settings Tabs -->
    <div class="settings-tabs" role="tablist" aria-label="Settings sections">
      <button 
        v-for="(tab, idx) in tabs" 
        :id="tab.id"
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        class="tab-button"
        role="tab"
        :aria-selected="activeTab === tab.id"
        :tabindex="activeTab === tab.id ? 0 : -1"
        :aria-controls="`panel-${tab.id}`"
        @click="activeTab = tab.id"
        @keydown="(e) => onTabKeydown(e, idx)"
      >
        {{ tab.label }}
      </button>
    </div>
    
    <!-- System Settings -->
    <div
      v-if="activeTab === 'system'"
      :id="'panel-system'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="system"
    >
      <div class="card">
        <div class="card-header">
          <h3>System Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="device-name">Device Name</label>
            <input 
              id="device-name" 
              v-model="systemSettings.device_name" 
              type="text"
              class="form-control"
              placeholder="LawnBerry Pi"
            >
          </div>
          
          <div class="form-group">
            <label for="timezone">Timezone</label>
            <select id="timezone" v-model="systemSettings.timezone" class="form-control">
              <option v-for="tz in timezoneOptions" :key="tz" :value="tz">
                {{ formatTimezoneLabel(tz) }}
              </option>
            </select>
            <small v-if="detectedTimezoneNote" class="form-text text-muted">
              {{ detectedTimezoneNote }}
            </small>
          </div>

          <div class="form-group">
            <label for="unit-system">Measurement Units</label>
            <select id="unit-system" v-model="systemSettings.ui.unit_system" class="form-control">
              <option value="metric">Metric (°C, m/s, meters)</option>
              <option value="imperial">Imperial (°F, mph, feet)</option>
            </select>
            <small class="form-text text-muted">
              Controls how telemetry is displayed across the dashboard.
            </small>
          </div>
          
          <div class="form-group">
            <label>
              <input 
                id="debug-mode-toggle" 
                v-model="systemSettings.debug_mode"
                type="checkbox"
                class="form-check-input"
                name="debug-mode"
              > 
              Enable Debug Mode
            </label>
          </div>
          
          <button
            class="btn btn-primary"
            :disabled="saving"
            aria-label="Save system settings"
            @click="saveSystemSettings"
          >
            {{ saving ? 'Saving...' : 'Save System Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Security Settings -->
    <div
      v-if="activeTab === 'security'"
      :id="'panel-security'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="security"
    >
      <div class="card">
        <div class="card-header">
          <h3>Security Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="auth-level">Authentication Level</label>
            <select id="auth-level" v-model="securitySettings.auth_level" class="form-control">
              <option value="password">Password Only</option>
              <option value="totp">Password + TOTP</option>
              <option value="google">Google Authentication</option>
              <option value="cloudflare">Cloudflare Tunnel Auth</option>
            </select>
            <small class="form-text text-muted">
              Higher levels provide better security for remote access
            </small>
          </div>
          
          <div class="form-group">
            <label for="session-timeout">Session Timeout (minutes)</label>
            <input 
              id="session-timeout" 
              v-model.number="securitySettings.session_timeout_minutes" 
              type="number"
              class="form-control"
              min="5" 
              max="1440"
            >
          </div>
          
          <div class="form-group">
            <label>
              <input 
                id="require-https-toggle" 
                v-model="securitySettings.require_https"
                type="checkbox"
                class="form-check-input"
                name="require-https"
              > 
              Require HTTPS
            </label>
          </div>
          
          <div class="form-group">
            <label>
              <input 
                id="auto-lock-control-toggle" 
                v-model="securitySettings.auto_lock_manual_control"
                type="checkbox"
                class="form-check-input"
                name="auto-lock-control"
              > 
              Auto-lock Manual Control
            </label>
          </div>
          
          <button
            class="btn btn-primary"
            :disabled="saving"
            aria-label="Save security settings"
            @click="saveSecuritySettings"
          >
            {{ saving ? 'Saving...' : 'Save Security Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Remote Access Settings -->
    <div
      v-if="activeTab === 'remote'"
      :id="'panel-remote'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="remote"
    >
      <div class="card">
        <div class="card-header">
          <h3>Remote Access Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="remote-method">Remote Access Method</label>
            <select id="remote-method" v-model="remoteSettings.method" class="form-control">
              <option value="none">Disabled</option>
              <option value="cloudflare">Cloudflare Tunnel</option>
              <option value="ngrok">Ngrok</option>
              <option value="custom">Custom Domain</option>
            </select>
          </div>
          
          <div v-if="remoteSettings.method === 'cloudflare'" class="remote-config">
            <div class="form-group">
              <label for="cloudflare-token">Cloudflare Tunnel Token</label>
              <input 
                id="cloudflare-token" 
                v-model="remoteSettings.cloudflare_token" 
                type="password"
                class="form-control"
                placeholder="Enter tunnel token"
              >
            </div>
          </div>
          
          <div v-if="remoteSettings.method === 'ngrok'" class="remote-config">
            <div class="form-group">
              <label for="ngrok-token">Ngrok Auth Token</label>
              <input 
                id="ngrok-token" 
                v-model="remoteSettings.ngrok_token" 
                type="password"
                class="form-control"
                placeholder="Enter ngrok token"
              >
            </div>
          </div>
          
          <div v-if="remoteSettings.method === 'custom'" class="remote-config">
            <div class="form-group">
              <label for="custom-domain">Custom Domain</label>
              <input 
                id="custom-domain" 
                v-model="remoteSettings.custom_domain" 
                type="text"
                class="form-control"
                placeholder="example.com"
              >
            </div>
            
            <div class="form-group">
              <label>
                <input 
                  id="auto-tls-toggle" 
                  v-model="remoteSettings.auto_tls"
                  type="checkbox"
                  class="form-check-input"
                  name="auto-tls"
                > 
                Automatic TLS (Let's Encrypt)
              </label>
            </div>
          </div>
          
          <div class="form-group">
            <label>
              <input 
                id="remote-access-toggle" 
                v-model="remoteSettings.enabled"
                type="checkbox"
                class="form-check-input"
                name="remote-access"
              > 
              Enable Remote Access
            </label>
          </div>
          
          <button
            class="btn btn-primary"
            :disabled="saving"
            aria-label="Save remote access settings"
            @click="saveRemoteSettings"
          >
            {{ saving ? 'Saving...' : 'Save Remote Access Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Maps Settings -->
    <div
      v-if="activeTab === 'maps'"
      :id="'panel-maps'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="maps"
    >
      <div class="card">
        <div class="card-header">
          <h3>Maps Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="maps-provider">Maps Provider</label>
            <select id="maps-provider" v-model="mapsSettings.provider" class="form-control">
              <option value="osm">OpenStreetMap (Free)</option>
              <option value="google">Google Maps</option>
              <option value="none">Disabled</option>
            </select>
          </div>
          
          <div v-if="mapsRequireGoogleApiKey" class="maps-config">
            <div class="form-group">
              <label for="google-api-key">Google Maps API Key</label>
              <input 
                id="google-api-key" 
                v-model="mapsSettings.google_api_key" 
                type="password"
                class="form-control"
                placeholder="Enter your Google Maps API key"
              >
              <small class="form-text text-muted">
                Required whenever the main map or Mission Planner uses Google Maps. Get your key at 
                <a href="https://developers.google.com/maps" target="_blank">Google Cloud Console</a>
              </small>
            </div>
            
            <div class="form-group">
              <label>
                <input 
                  id="google-billing-warnings" 
                  v-model="mapsSettings.google_billing_warnings"
                  type="checkbox"
                  class="form-check-input"
                  name="google-billing-warnings"
                > 
                Show billing warnings
              </label>
            </div>
          </div>
          
          <div class="form-group">
            <label for="map-style">Map Style</label>
            <select id="map-style" v-model="mapsSettings.style" class="form-control">
              <option value="standard">Standard</option>
              <option value="satellite">Satellite</option>
              <option value="hybrid">Hybrid</option>
              <option value="terrain">Terrain</option>
            </select>
          </div>

          <div class="maps-config">
            <div class="form-group">
              <label for="mission-planner-provider">Mission Planner Provider</label>
              <select id="mission-planner-provider" v-model="mapsSettings.mission_planner.provider" class="form-control">
                <option value="osm">OpenStreetMap (Free)</option>
                <option value="google">Google Maps</option>
                <option value="none">Disabled</option>
              </select>
              <small class="form-text text-muted">
                Lets `/mission-planner` use its own provider without changing the main `/maps` page. Google still uses the shared API key above.
              </small>
            </div>

            <div class="form-group">
              <label for="mission-planner-style">Mission Planner Style</label>
              <select id="mission-planner-style" v-model="mapsSettings.mission_planner.style" class="form-control">
                <option value="standard">Standard</option>
                <option value="satellite">Satellite</option>
                <option value="hybrid">Hybrid</option>
                <option value="terrain">Terrain</option>
              </select>
              <small class="form-text text-muted">
                Use this to keep everyday maps on OSM while reserving higher-cost Google imagery for close waypoint placement in mission planning.
              </small>
            </div>
          </div>
          
          <button
            class="btn btn-primary"
            :disabled="saving"
            aria-label="Save maps settings"
            @click="saveMapsSettings"
          >
            {{ saving ? 'Saving...' : 'Save Maps Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- GPS Policy Settings -->
    <div
      v-if="activeTab === 'gps'"
      :id="'panel-gps'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="gps"
    >
      <div class="card">
        <div class="card-header">
          <h3>GPS Policy Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="gps-loss-policy">GPS Loss Policy</label>
            <select id="gps-loss-policy" v-model="gpsSettings.gps_loss_policy" class="form-control">
              <option value="stop">Stop Immediately</option>
              <option value="return_home">Return to Base</option>
              <option value="dead_reckoning">Continue with Dead Reckoning</option>
            </select>
          </div>
          
          <div v-if="gpsSettings.gps_loss_policy === 'dead_reckoning'" class="gps-config">
            <div class="form-group">
              <label for="dead-reckoning-duration">Dead Reckoning Duration (minutes)</label>
              <input 
                id="dead-reckoning-duration" 
                v-model.number="gpsSettings.dead_reckoning_duration_minutes" 
                type="number"
                class="form-control"
                min="1" 
                max="10"
              >
              <small class="form-text text-muted">
                Maximum time to continue without GPS (recommended: ≤2 minutes)
              </small>
            </div>
            
            <div class="form-group">
              <label for="reduced-speed-factor">Reduced Speed Factor</label>
              <input 
                id="reduced-speed-factor" 
                v-model.number="gpsSettings.reduced_speed_factor" 
                type="number"
                class="form-control"
                min="0.1" 
                max="1.0" 
                step="0.1"
              >
              <small class="form-text text-muted">
                Speed multiplier during dead reckoning (0.1 = 10% speed)
              </small>
            </div>
          </div>
          
          <div class="form-group">
            <label for="accuracy-threshold">GPS Accuracy Threshold (meters)</label>
            <input 
              id="accuracy-threshold" 
              v-model.number="gpsSettings.accuracy_threshold_meters" 
              type="number"
              class="form-control"
              min="1" 
              max="10"
            >
          </div>
          
          <button
            class="btn btn-primary"
            :disabled="saving"
            aria-label="Save GPS policy settings"
            @click="saveGpsSettings"
          >
            {{ saving ? 'Saving...' : 'Save GPS Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Safety Tab -->
    <div
      v-if="activeTab === 'safety'"
      :id="'panel-safety'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="safety"
    >
      <div class="card">
        <div class="card-header">
          <h3>Obstacle Detection</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="obstacle-distance">Obstacle Stop Distance</label>
            <p class="form-text">Minimum distance from Time-of-Flight sensors before the mower triggers an obstacle stop. Reduce false positives by increasing this value; lower it for tighter obstacle avoidance.</p>
            <div class="input-with-unit">
              <input
                id="obstacle-distance"
                type="number"
                class="form-control"
                :value="obstacleDistanceDisplay"
                :step="systemSettings.ui.unit_system === 'imperial' ? 0.5 : 1"
                :min="systemSettings.ui.unit_system === 'imperial' ? 2 : 50"
                :max="systemSettings.ui.unit_system === 'imperial' ? 48 : 1200"
                @input="setObstacleDistanceFromDisplay(($event.target as HTMLInputElement).value)"
              >
              <span class="unit-label">{{ systemSettings.ui.unit_system === 'imperial' ? 'inches' : 'mm' }}</span>
            </div>
            <p class="form-text dim">
              Current: {{ obstacleDistanceDisplay }} {{ systemSettings.ui.unit_system === 'imperial' ? 'in' : 'mm' }}
              ({{ (safetySettings.tof_obstacle_distance_meters * 1000).toFixed(0) }} mm / {{ safetySettings.tof_obstacle_distance_meters.toFixed(3) }} m)
            </p>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Tilt &amp; Battery</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="tilt-threshold">Tilt Threshold (degrees)</label>
            <p class="form-text">Maximum tilt angle before the safety interlock triggers.</p>
            <input
              id="tilt-threshold"
              v-model.number="safetySettings.tilt_threshold_degrees"
              type="number"
              class="form-control"
              step="1"
              min="10"
              max="45"
            >
          </div>
          <div class="form-group">
            <label for="battery-low">Battery Low Voltage (V)</label>
            <p class="form-text">Voltage at which low-battery warning activates.</p>
            <input
              id="battery-low"
              v-model.number="safetySettings.battery_low_voltage"
              type="number"
              class="form-control"
              step="0.1"
              min="10"
              max="14"
            >
          </div>
          <div class="form-group">
            <label for="battery-critical">Battery Critical Voltage (V)</label>
            <p class="form-text">Voltage at which emergency stop triggers. Must be below low voltage.</p>
            <input
              id="battery-critical"
              v-model.number="safetySettings.battery_critical_voltage"
              type="number"
              class="form-control"
              step="0.1"
              min="9"
              max="14"
            >
          </div>
          <div class="form-group">
            <label for="geofence-buffer">Geofence Buffer (meters)</label>
            <p class="form-text">Extra margin around yard boundary before geofence violation triggers.</p>
            <input
              id="geofence-buffer"
              v-model.number="safetySettings.geofence_buffer_meters"
              type="number"
              class="form-control"
              step="0.1"
              min="0"
              max="5"
            >
          </div>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-primary" :disabled="saving" @click="saveSafetySettings">
          {{ saving ? 'Saving...' : 'Save Safety Settings' }}
        </button>
      </div>
    </div>

    <!-- Diagnostics Tab -->
    <div
      v-if="activeTab === 'diagnostics'"
      :id="'panel-diagnostics'"
      class="settings-section"
      role="tabpanel"
      aria-labelledby="diagnostics"
    >
      <div class="card">
        <div class="card-header">
          <h3>Runtime Diagnostics</h3>
        </div>
        <div class="card-body">
          <p class="form-text">NTRIP and GPS RTK visibility. For full-page view, <router-link to="/rtk">open RTK Diagnostics</router-link>.</p>
          <RtkDiagnosticsPanel />
        </div>
      </div>
    </div>

    <!-- Status indicator -->
    <div
      v-if="saveMessage"
      class="alert"
      :class="saveSuccess ? 'alert-success' : 'alert-danger'"
      role="status"
      aria-live="polite"
    >
      {{ saveMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useApiService } from '@/services/api'
import { useToastStore } from '@/stores/toast'
import { usePreferencesStore } from '@/stores/preferences'
import RtkDiagnosticsPanel from '@/components/RtkDiagnosticsPanel.vue'

const api = useApiService()
const toast = useToastStore()
const preferences = usePreferencesStore()
preferences.ensureInitialized()

// State
const activeTab = ref('system')
const saving = ref(false)
const saveMessage = ref('')
const saveSuccess = ref(false)

// Tabs configuration
const tabs = [
  { id: 'system', label: 'System' },
  { id: 'security', label: 'Security' },
  { id: 'remote', label: 'Remote Access' },
  { id: 'maps', label: 'Maps' },
  { id: 'gps', label: 'GPS Policy' },
  { id: 'safety', label: 'Safety' },
  { id: 'diagnostics', label: 'Diagnostics' }
]

// Settings objects
const systemSettings = ref({
  device_name: 'LawnBerry Pi',
  timezone: 'UTC',
  debug_mode: false,
  ui: {
    unit_system: 'metric',
    theme: 'retro-amber',
    auto_refresh: true,
    map_provider: 'google'
  }
})

const timezoneOptions = ref<string[]>([
  'UTC',
  'Etc/GMT',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Australia/Sydney'
])

const detectedTimezoneSource = ref<string | null>(null)
const timezoneAppliedAutomatically = ref(false)
let suppressTimezoneWatch = false

function ensureTimezoneOption(tz: string | null | undefined) {
  if (!tz) {
    return
  }
  const normalized = String(tz).trim()
  if (!normalized) {
    return
  }
  if (!timezoneOptions.value.includes(normalized)) {
    const unique = new Set(timezoneOptions.value)
    unique.add(normalized)
    timezoneOptions.value = Array.from(unique).sort((a, b) => {
      if (a === 'UTC') return -1
      if (b === 'UTC') return 1
      return a.localeCompare(b)
    })
  }
}

function formatTimezoneLabel(tz: string): string {
  return tz.replace(/_/g, ' ')
}

const detectedTimezoneNote = computed(() => {
  if (!timezoneAppliedAutomatically.value || !detectedTimezoneSource.value) {
    return ''
  }
  switch (detectedTimezoneSource.value) {
    case 'gps':
      return 'Detected automatically from mower GPS fix.'
    case 'system':
      return 'Detected from mower operating system timezone.'
    default:
      return 'Detected automatically.'
  }
})

const browserTimezone = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch (error) {
    console.debug('Unable to resolve browser timezone', error)
    return undefined
  }
})()

if (browserTimezone) {
  ensureTimezoneOption(browserTimezone)
}

function applyDetectedTimezone(tz: string, source?: string) {
  suppressTimezoneWatch = true
  timezoneAppliedAutomatically.value = true
  detectedTimezoneSource.value = source ?? null
  systemSettings.value.timezone = tz
  ensureTimezoneOption(tz)
}

const securitySettings = ref({
  auth_level: 'password',
  session_timeout_minutes: 60,
  require_https: false,
  auto_lock_manual_control: true
})

const remoteSettings = ref({
  method: 'none',
  enabled: false,
  cloudflare_token: '',
  ngrok_token: '',
  custom_domain: '',
  auto_tls: true
})

const mapsSettings = ref({
  provider: 'osm',
  google_api_key: '',
  google_billing_warnings: true,
  style: 'standard',
  mission_planner: {
    provider: 'osm',
    style: 'standard',
  },
})

const mapsRequireGoogleApiKey = computed(() => {
  return mapsSettings.value.provider === 'google' || mapsSettings.value.mission_planner.provider === 'google'
})

function looksLikeGoogleOAuthClientId(value: string): boolean {
  return String(value || '').trim().toLowerCase().endsWith('.apps.googleusercontent.com')
}

const gpsSettings = ref({
  gps_loss_policy: 'dead_reckoning',
  dead_reckoning_duration_minutes: 2,
  reduced_speed_factor: 0.5,
  accuracy_threshold_meters: 3
})

const safetySettings = ref({
  tof_obstacle_distance_meters: 0.2,
  tilt_threshold_degrees: 30.0,
  geofence_buffer_meters: 0.5,
  battery_low_voltage: 12.2,
  battery_critical_voltage: 11.8,
  motor_current_max_amps: 5.0,
  high_temperature_celsius: 80.0,
})

const obstacleDistanceDisplay = computed(() => {
  const meters = safetySettings.value.tof_obstacle_distance_meters
  if (systemSettings.value.ui.unit_system === 'imperial') {
    return parseFloat((meters * 39.3701).toFixed(1))
  }
  return Math.round(meters * 1000)
})

function setObstacleDistanceFromDisplay(raw: string) {
  const val = parseFloat(raw)
  if (isNaN(val) || val <= 0) return
  if (systemSettings.value.ui.unit_system === 'imperial') {
    safetySettings.value.tof_obstacle_distance_meters = val / 39.3701
  } else {
    safetySettings.value.tof_obstacle_distance_meters = val / 1000
  }
}

watch(
  () => systemSettings.value.ui.unit_system,
  (value) => {
    if (value === 'metric' || value === 'imperial') {
      preferences.setUnitSystem(value)
    }
  },
  { immediate: true }
)

watch(
  () => systemSettings.value.timezone,
  (value, oldValue) => {
    ensureTimezoneOption(value)
    if (suppressTimezoneWatch) {
      suppressTimezoneWatch = false
      return
    }
    if (oldValue !== undefined && value !== oldValue) {
      timezoneAppliedAutomatically.value = false
    }
  },
  { immediate: true }
)

// Load settings
async function loadAllSettings() {
  try {
    const [system, security, remote, maps, gps, safety] = await Promise.all([
      api.get('/api/v2/settings/system'),
      api.get('/api/v2/settings/security'),
      api.get('/api/v2/settings/remote-access'),
      api.get('/api/v2/settings/maps'),
      api.get('/api/v2/settings/gps-policy'),
      api.get('/api/v2/settings/safety')
    ])
    
    const systemData = system.data || {}
    const timezoneFromApi = typeof systemData.timezone === 'string' ? systemData.timezone : undefined
    const timezoneSourceFromApi = typeof systemData.timezone_source === 'string' ? systemData.timezone_source : undefined

    systemSettings.value = {
      ...systemSettings.value,
      ...systemData,
      ui: {
        ...systemSettings.value.ui,
        ...(systemData.ui || {})
      }
    }
    ensureTimezoneOption(systemSettings.value.timezone)

    if (timezoneFromApi && timezoneSourceFromApi && timezoneSourceFromApi !== 'manual' && timezoneSourceFromApi !== 'default') {
      applyDetectedTimezone(timezoneFromApi, timezoneSourceFromApi)
    } else if (timezoneSourceFromApi === 'manual') {
      detectedTimezoneSource.value = null
      timezoneAppliedAutomatically.value = false
    }
    securitySettings.value = { ...securitySettings.value, ...security.data }
    remoteSettings.value = { ...remoteSettings.value, ...remote.data }
    mapsSettings.value = {
      ...mapsSettings.value,
      ...maps.data,
      mission_planner: {
        ...mapsSettings.value.mission_planner,
        ...(maps.data?.mission_planner || {}),
      },
    }
    gpsSettings.value = { ...gpsSettings.value, ...gps.data }
    if (safety.data) {
      safetySettings.value = { ...safetySettings.value, ...safety.data }
    }
    // Auto-detect timezone from mower if unset or left at default
    const needsAutoDetect = (!systemSettings.value.timezone || systemSettings.value.timezone.toUpperCase() === 'UTC') && (!timezoneSourceFromApi || timezoneSourceFromApi === 'default')
    if (needsAutoDetect) {
      await maybeApplyDetectedTimezone()
    }
    toast.show('Settings loaded', 'info', 2000)
  } catch (error) {
    console.error('Failed to load settings:', error)
    showMessage('Failed to load settings', false)
    toast.show('Failed to load settings', 'error', 4000)
  }
}

async function maybeApplyDetectedTimezone() {
  try {
    const currentTz = String(systemSettings.value.timezone || '').trim()
    if (currentTz) {
      ensureTimezoneOption(currentTz)
    }
    // Treat 'UTC' and empty as needing detection
    if (!currentTz || currentTz.toUpperCase() === 'UTC') {
      const resp = await api.get('/api/v2/system/timezone')
      const tz: string | undefined = resp?.data?.timezone
      const source: string | undefined = resp?.data?.source
      if (tz && typeof tz === 'string' && tz.includes('/')) {
        applyDetectedTimezone(tz, source)
        return
      }
    }
  } catch (e) {
    // Non-fatal: keep default
    console.debug('Timezone auto-detect failed; leaving default', e)
  }
}

// Save functions
async function saveSystemSettings() {
  await saveSettings('/api/v2/settings/system', systemSettings.value)
}

async function saveSecuritySettings() {
  await saveSettings('/api/v2/settings/security', securitySettings.value)
}

async function saveRemoteSettings() {
  await saveSettings('/api/v2/settings/remote-access', remoteSettings.value)
}

async function saveMapsSettings() {
  const googleApiKey = String(mapsSettings.value.google_api_key || '').trim()
  if (mapsRequireGoogleApiKey.value && !googleApiKey) {
    showMessage('Enter a Google Maps API key before enabling Google Maps for the main map or Mission Planner.', false)
    toast.show('Google Maps API key required', 'error', 4000)
    return
  }
  if (mapsRequireGoogleApiKey.value && looksLikeGoogleOAuthClientId(googleApiKey)) {
    showMessage('Enter a Google Maps API key, not a Google OAuth client ID.', false)
    toast.show('Google Maps API key is invalid', 'error', 4500)
    return
  }
  await saveSettings('/api/v2/settings/maps', mapsSettings.value)
}

async function saveGpsSettings() {
  await saveSettings('/api/v2/settings/gps-policy', gpsSettings.value)
}

async function saveSafetySettings() {
  await saveSettings('/api/v2/settings/safety', safetySettings.value)
}

async function saveSettings(endpoint: string, data: any) {
  saving.value = true
  try {
    await api.put(endpoint, data)
    showMessage('Settings saved successfully!', true)
    toast.show('Settings saved', 'success', 2500)
  } catch (error) {
    console.error('Failed to save settings:', error)
    showMessage('Failed to save settings', false)
    toast.show('Failed to save settings', 'error', 4000)
  } finally {
    saving.value = false
  }
}

function showMessage(message: string, success: boolean) {
  saveMessage.value = message
  saveSuccess.value = success
  setTimeout(() => {
    saveMessage.value = ''
  }, 3000)
}

onMounted(() => {
  loadAllSettings()
})

function onTabKeydown(e: KeyboardEvent, idx: number) {
  if (e.key === 'ArrowRight') {
    const next = (idx + 1) % tabs.length
    activeTab.value = tabs[next].id
    e.preventDefault()
  } else if (e.key === 'ArrowLeft') {
    const prev = (idx - 1 + tabs.length) % tabs.length
    activeTab.value = tabs[prev].id
    e.preventDefault()
  }
}
</script>

<style scoped>
.settings-view {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
}

.settings-tabs {
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

.tab-button:focus-visible {
  outline: 2px solid var(--accent-green);
  outline-offset: 2px;
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

.settings-section {
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

@media (prefers-reduced-motion: reduce) {
  .tab-button, .btn {
    transition: none !important;
  }
  .settings-section {
    animation: none !important;
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
}

.card-header h3 {
  margin: 0;
  color: var(--accent-green);
  font-size: 1.25rem;
}

.card-body {
  padding: 1.5rem;
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

.form-control::placeholder {
  color: var(--text-muted);
}

.form-check-input {
  margin-right: 0.5rem;
  width: auto;
}

.form-text {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn:focus-visible {
  outline: 2px solid var(--accent-green);
  outline-offset: 2px;
}

.btn-primary {
  background: var(--accent-green);
  color: var(--primary-dark);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-green-hover);
  transform: translateY(-2px);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.remote-config,
.maps-config,
.gps-config {
  margin-left: 1rem;
  padding-left: 1rem;
  border-left: 3px solid var(--accent-green);
}

.alert {
  padding: 1rem;
  border-radius: 4px;
  margin-top: 1rem;
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
  .settings-tabs {
    flex-direction: column;
  }
  
  .tab-button {
    padding: 0.75rem 1rem;
    text-align: left;
  }
  
  .remote-config,
  .maps-config,
  .gps-config {
    margin-left: 0;
    padding-left: 0;
    border-left: none;
    border-top: 3px solid var(--accent-green);
    padding-top: 1rem;
    margin-top: 1rem;
  }
}

.input-with-unit {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  max-width: 300px;
}

.input-with-unit .form-control {
  flex: 1;
}

.unit-label {
  font-size: 0.9rem;
  color: var(--text-secondary, #888);
  white-space: nowrap;
}

.form-text.dim {
  opacity: 0.7;
  font-size: 0.8rem;
}
</style>
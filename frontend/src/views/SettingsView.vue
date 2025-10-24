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
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        class="tab-button"
        role="tab"
        :id="tab.id"
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
    <div v-if="activeTab === 'system'" class="settings-section" :id="'panel-system'" role="tabpanel" aria-labelledby="system">
      <div class="card">
        <div class="card-header">
          <h3>System Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="device-name">Device Name</label>
            <input 
              v-model="systemSettings.device_name" 
              type="text" 
              class="form-control"
              id="device-name"
              placeholder="LawnBerry Pi"
            >
          </div>
          
          <div class="form-group">
            <label for="timezone">Timezone</label>
            <select v-model="systemSettings.timezone" id="timezone" class="form-control">
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
            <select v-model="systemSettings.ui.unit_system" id="unit-system" class="form-control">
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
                v-model="systemSettings.debug_mode" 
                type="checkbox"
                class="form-check-input"
                id="debug-mode-toggle"
                name="debug-mode"
              > 
              Enable Debug Mode
            </label>
          </div>
          
          <button class="btn btn-primary" :disabled="saving" @click="saveSystemSettings" aria-label="Save system settings">
            {{ saving ? 'Saving...' : 'Save System Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Security Settings -->
    <div v-if="activeTab === 'security'" class="settings-section" :id="'panel-security'" role="tabpanel" aria-labelledby="security">
      <div class="card">
        <div class="card-header">
          <h3>Security Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="auth-level">Authentication Level</label>
            <select v-model="securitySettings.auth_level" id="auth-level" class="form-control">
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
              v-model.number="securitySettings.session_timeout_minutes" 
              type="number" 
              class="form-control"
              id="session-timeout"
              min="5" 
              max="1440"
            >
          </div>
          
          <div class="form-group">
            <label>
              <input 
                v-model="securitySettings.require_https" 
                type="checkbox"
                class="form-check-input"
                id="require-https-toggle"
                name="require-https"
              > 
              Require HTTPS
            </label>
          </div>
          
          <div class="form-group">
            <label>
              <input 
                v-model="securitySettings.auto_lock_manual_control" 
                type="checkbox"
                class="form-check-input"
                id="auto-lock-control-toggle"
                name="auto-lock-control"
              > 
              Auto-lock Manual Control
            </label>
          </div>
          
          <button class="btn btn-primary" :disabled="saving" @click="saveSecuritySettings" aria-label="Save security settings">
            {{ saving ? 'Saving...' : 'Save Security Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Remote Access Settings -->
    <div v-if="activeTab === 'remote'" class="settings-section" :id="'panel-remote'" role="tabpanel" aria-labelledby="remote">
      <div class="card">
        <div class="card-header">
          <h3>Remote Access Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="remote-method">Remote Access Method</label>
            <select v-model="remoteSettings.method" id="remote-method" class="form-control">
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
                v-model="remoteSettings.cloudflare_token" 
                type="password" 
                class="form-control"
                id="cloudflare-token"
                placeholder="Enter tunnel token"
              >
            </div>
          </div>
          
          <div v-if="remoteSettings.method === 'ngrok'" class="remote-config">
            <div class="form-group">
              <label for="ngrok-token">Ngrok Auth Token</label>
              <input 
                v-model="remoteSettings.ngrok_token" 
                type="password" 
                class="form-control"
                id="ngrok-token"
                placeholder="Enter ngrok token"
              >
            </div>
          </div>
          
          <div v-if="remoteSettings.method === 'custom'" class="remote-config">
            <div class="form-group">
              <label for="custom-domain">Custom Domain</label>
              <input 
                v-model="remoteSettings.custom_domain" 
                type="text" 
                class="form-control"
                id="custom-domain"
                placeholder="example.com"
              >
            </div>
            
            <div class="form-group">
              <label>
                <input 
                  v-model="remoteSettings.auto_tls" 
                  type="checkbox"
                    class="form-check-input"
                    id="auto-tls-toggle"
                    name="auto-tls"
                > 
                Automatic TLS (Let's Encrypt)
              </label>
            </div>
          </div>
          
          <div class="form-group">
            <label>
              <input 
                v-model="remoteSettings.enabled" 
                type="checkbox"
                class="form-check-input"
                id="remote-access-toggle"
                name="remote-access"
              > 
              Enable Remote Access
            </label>
          </div>
          
          <button class="btn btn-primary" :disabled="saving" @click="saveRemoteSettings" aria-label="Save remote access settings">
            {{ saving ? 'Saving...' : 'Save Remote Access Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Maps Settings -->
    <div v-if="activeTab === 'maps'" class="settings-section" :id="'panel-maps'" role="tabpanel" aria-labelledby="maps">
      <div class="card">
        <div class="card-header">
          <h3>Maps Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="maps-provider">Maps Provider</label>
            <select v-model="mapsSettings.provider" id="maps-provider" class="form-control">
              <option value="osm">OpenStreetMap (Free)</option>
              <option value="google">Google Maps</option>
              <option value="none">Disabled</option>
            </select>
          </div>
          
          <div v-if="mapsSettings.provider === 'google'" class="maps-config">
            <div class="form-group">
              <label for="google-api-key">Google Maps API Key</label>
              <input 
                v-model="mapsSettings.google_api_key" 
                type="password" 
                class="form-control"
                id="google-api-key"
                placeholder="Enter your Google Maps API key"
              >
              <small class="form-text text-muted">
                Required for Google Maps features. Get your key at 
                <a href="https://developers.google.com/maps" target="_blank">Google Cloud Console</a>
              </small>
            </div>
            
            <div class="form-group">
              <label>
                <input 
                  v-model="mapsSettings.google_billing_warnings" 
                  type="checkbox"
                  class="form-check-input"
                  id="google-billing-warnings"
                  name="google-billing-warnings"
                > 
                Show billing warnings
              </label>
            </div>
          </div>
          
          <div class="form-group">
            <label for="map-style">Map Style</label>
            <select v-model="mapsSettings.style" id="map-style" class="form-control">
              <option value="standard">Standard</option>
              <option value="satellite">Satellite</option>
              <option value="hybrid">Hybrid</option>
              <option value="terrain">Terrain</option>
            </select>
          </div>
          
          <button class="btn btn-primary" :disabled="saving" @click="saveMapsSettings" aria-label="Save maps settings">
            {{ saving ? 'Saving...' : 'Save Maps Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- GPS Policy Settings -->
    <div v-if="activeTab === 'gps'" class="settings-section" :id="'panel-gps'" role="tabpanel" aria-labelledby="gps">
      <div class="card">
        <div class="card-header">
          <h3>GPS Policy Settings</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label for="gps-loss-policy">GPS Loss Policy</label>
            <select v-model="gpsSettings.gps_loss_policy" id="gps-loss-policy" class="form-control">
              <option value="stop">Stop Immediately</option>
              <option value="return_home">Return to Base</option>
              <option value="dead_reckoning">Continue with Dead Reckoning</option>
            </select>
          </div>
          
          <div v-if="gpsSettings.gps_loss_policy === 'dead_reckoning'" class="gps-config">
            <div class="form-group">
              <label for="dead-reckoning-duration">Dead Reckoning Duration (minutes)</label>
              <input 
                v-model.number="gpsSettings.dead_reckoning_duration_minutes" 
                type="number" 
                class="form-control"
                id="dead-reckoning-duration"
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
                v-model.number="gpsSettings.reduced_speed_factor" 
                type="number" 
                class="form-control"
                id="reduced-speed-factor"
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
              v-model.number="gpsSettings.accuracy_threshold_meters" 
              type="number" 
              class="form-control"
              id="accuracy-threshold"
              min="1" 
              max="10"
            >
          </div>
          
          <button class="btn btn-primary" :disabled="saving" @click="saveGpsSettings" aria-label="Save GPS policy settings">
            {{ saving ? 'Saving...' : 'Save GPS Settings' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Status indicator -->
    <div v-if="saveMessage" class="alert" :class="saveSuccess ? 'alert-success' : 'alert-danger'" role="status" aria-live="polite">
      {{ saveMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useApiService } from '@/services/api'
import { useToastStore } from '@/stores/toast'
import { usePreferencesStore } from '@/stores/preferences'

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
  { id: 'gps', label: 'GPS Policy' }
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
  style: 'standard'
})

const gpsSettings = ref({
  gps_loss_policy: 'dead_reckoning',
  dead_reckoning_duration_minutes: 2,
  reduced_speed_factor: 0.5,
  accuracy_threshold_meters: 3
})

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
    const [system, security, remote, maps, gps] = await Promise.all([
      api.get('/api/v2/settings/system'),
      api.get('/api/v2/settings/security'),
      api.get('/api/v2/settings/remote-access'),
      api.get('/api/v2/settings/maps'),
      api.get('/api/v2/settings/gps-policy')
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
    mapsSettings.value = { ...mapsSettings.value, ...maps.data }
    gpsSettings.value = { ...gpsSettings.value, ...gps.data }
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
  await saveSettings('/api/v2/settings/maps', mapsSettings.value)
}

async function saveGpsSettings() {
  await saveSettings('/api/v2/settings/gps-policy', gpsSettings.value)
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
</style>
<template>
  <div class="maps-view">
    <div class="page-header">
      <h1>Map Setup</h1>
      <p class="text-muted">Configure map providers, API keys, and manage pin assets</p>
    </div>

    <!-- Map Provider Configuration -->
    <div class="card">
      <div class="card-header">
        <h3>Map Provider Configuration</h3>
      </div>
      <div class="card-body">
        <div class="form-group">
          <label>Map Provider</label>
          <select v-model="settings.provider" class="form-control" @change="onProviderChange">
            <option value="osm">OpenStreetMap (Free)</option>
            <option value="google">Google Maps</option>
            <option value="none">Disabled</option>
          </select>
        </div>

        <!-- Google Maps Configuration -->
        <div v-if="settings.provider === 'google'" class="provider-config">
          <div class="form-group">
            <label>Google Maps API Key</label>
            <div class="input-group">
              <input 
                v-model="settings.google_api_key" 
                :type="showApiKey ? 'text' : 'password'"
                class="form-control"
                placeholder="Enter your Google Maps API key"
              >
              <button 
                type="button" 
                class="btn btn-secondary"
                @click="showApiKey = !showApiKey"
              >
                {{ showApiKey ? '👁️' : '👁️‍🗨️' }}
              </button>
            </div>
            <small class="form-text text-muted">
              Get your API key at 
              <a href="https://developers.google.com/maps/documentation/javascript/get-api-key" target="_blank">
                Google Cloud Console
              </a>
            </small>
          </div>

          <div class="form-group">
            <label>
              <input 
                v-model="settings.google_billing_warnings" 
                type="checkbox"
                class="form-check-input"
              > 
              Show billing warnings
            </label>
            <small class="form-text text-muted">
              Warn when approaching API usage limits
            </small>
          </div>

          <div v-if="apiStatus" class="api-status">
            <div class="status-indicator" :class="apiStatus.valid ? 'status-success' : 'status-error'">
              {{ apiStatus.valid ? '✅ API Key Valid' : '❌ API Key Invalid' }}
            </div>
            <div v-if="apiStatus.message" class="status-message">
              {{ apiStatus.message }}
            </div>
          </div>
        </div>

        <!-- Map Style Configuration -->
        <div v-if="settings.provider !== 'none'" class="form-group">
          <label>Map Style</label>
          <select v-model="settings.style" class="form-control">
            <option value="standard">Standard</option>
            <option value="satellite">Satellite</option>
            <option value="hybrid">Hybrid</option>
            <option value="terrain">Terrain</option>
          </select>
        </div>

        <div class="action-buttons">
          <button class="btn btn-info" :disabled="testing" @click="testConnection">
            {{ testing ? 'Testing...' : 'Test Connection' }}
          </button>
          <button class="btn btn-primary" :disabled="saving" @click="saveSettings">
            {{ saving ? 'Saving...' : 'Save Settings' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Map Preview -->
    <div v-if="settings.provider !== 'none'" class="card">
      <div class="card-header">
        <h3>Map Preview</h3>
      </div>
      <div class="card-body">
        <div class="map-preview">
          <div class="preview-controls">
            <div class="coordinate-inputs">
              <label>Latitude:</label>
              <input 
                v-model.number="previewLat" 
                type="number" 
                step="0.0001"
                class="form-control-sm"
              >
              <label>Longitude:</label>
              <input 
                v-model.number="previewLon" 
                type="number" 
                step="0.0001"
                class="form-control-sm"
              >
              <label>Zoom:</label>
              <input 
                v-model.number="previewZoom" 
                type="number" 
                min="1" 
                max="20"
                class="form-control-sm"
              >
            </div>
          </div>
          
          <div class="tile-preview">
            <div v-if="previewError" class="preview-error">
              {{ previewError }}
            </div>
            <img 
              v-else-if="previewUrl"
              :src="previewUrl" 
              alt="Map tile preview"
              @error="onPreviewError"
              @load="onPreviewLoad"
            >
            <div v-else class="preview-error">
              Preview unavailable for current provider/style; using editor map below.
            </div>
            <div class="preview-meta">
              Provider: {{ settings.provider.toUpperCase() }} | 
              Style: {{ settings.style }} |
              Zoom: {{ previewZoom }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Boundary & Zone Editor -->
    <div v-if="settings.provider !== 'none'" class="card">
      <div class="card-header">
        <h3>Boundary & Zone Editor</h3>
      </div>
      <div class="card-body" style="height: 480px;">
        <BoundaryEditor />
      </div>
    </div>

    <!-- Pin Asset Management -->
    <div class="card">
      <div class="card-header">
        <h3>Pin Asset Management</h3>
      </div>
      <div class="card-body">
        <div class="pin-categories">
          <div v-for="category in pinCategories" :key="category.id" class="category">
            <div class="category-header">
              <h4>{{ category.name }}</h4>
              <button class="btn btn-sm btn-primary" @click="addPin(category.id)">
                Add Pin
              </button>
            </div>
            
            <div class="pin-list">
              <div 
                v-for="pin in category.pins" 
                :key="pin.id"
                class="pin-item"
                :class="{ active: selectedPin?.id === pin.id }"
                @click="selectPin(pin)"
              >
                <div class="pin-icon">{{ pin.icon }}</div>
                <div class="pin-info">
                  <div class="pin-name">{{ pin.name }}</div>
                  <div class="pin-coords">{{ pin.lat.toFixed(6) }}, {{ pin.lon.toFixed(6) }}</div>
                </div>
                <div class="pin-actions">
                  <button class="btn btn-xs btn-secondary" @click.stop="editPin(pin)">
                    ✏️
                  </button>
                  <button class="btn btn-xs btn-danger" @click.stop="deletePin(pin)">
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Pin Editor Modal -->
    <div v-if="showPinEditor" class="modal-overlay" @click="closePinEditor">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ editingPin ? 'Edit Pin' : 'Add Pin' }}</h3>
          <button class="btn btn-sm btn-secondary" @click="closePinEditor">✖️</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>Pin Name</label>
            <input v-model="pinForm.name" type="text" class="form-control">
          </div>
          
          <div class="form-group">
            <label>Category</label>
            <select v-model="pinForm.category" class="form-control">
              <option v-for="cat in pinCategories" :key="cat.id" :value="cat.id">
                {{ cat.name }}
              </option>
            </select>
          </div>
          
          <div class="form-group">
            <label>Icon</label>
            <div class="icon-picker">
              <button 
                v-for="icon in availableIcons" 
                :key="icon"
                class="icon-button"
                :class="{ active: pinForm.icon === icon }"
                @click="pinForm.icon = icon"
              >
                {{ icon }}
              </button>
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>Latitude</label>
              <input
                v-model.number="pinForm.lat"
                type="number"
                step="0.000001"
                class="form-control"
              >
            </div>
            <div class="form-group">
              <label>Longitude</label>
              <input
                v-model.number="pinForm.lon"
                type="number"
                step="0.000001"
                class="form-control"
              >
            </div>
          </div>
          
          <div class="form-group">
            <label>Description</label>
            <textarea v-model="pinForm.description" class="form-control" rows="3" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closePinEditor">Cancel</button>
          <button class="btn btn-primary" @click="savePin">Save Pin</button>
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
import { useApiService } from '@/services/api'
import BoundaryEditor from '@/components/map/BoundaryEditor.vue'

const api = useApiService()

// State
const settings = ref({
  provider: 'osm',
  google_api_key: '',
  google_billing_warnings: true,
  style: 'standard'
})

const showApiKey = ref(false)
const apiStatus = ref<{valid: boolean, message?: string} | null>(null)
const testing = ref(false)
const saving = ref(false)
const statusMessage = ref('')
const statusSuccess = ref(false)

// Preview state
const previewLat = ref(37.7749)
const previewLon = ref(-122.4194)
const previewZoom = ref(15)
const previewError = ref('')

// Pin management state
const showPinEditor = ref(false)
const editingPin = ref<any>(null)
const selectedPin = ref<any>(null)
const pinForm = ref({
  name: '',
  category: 'waypoints',
  icon: '📍',
  lat: 0,
  lon: 0,
  description: ''
})

const pinCategories = ref([
  {
    id: 'waypoints',
    name: 'Waypoints',
    pins: [
      { id: 1, name: 'Home Base', icon: '🏠', lat: 37.7749, lon: -122.4194, description: 'Charging station' },
  { id: 2, name: 'Lawn Entry', icon: '🚪', lat: 37.7750, lon: -122.4195, description: 'Main entrance' }
    ]
  },
  {
    id: 'zones',
    name: 'Mowing Zones',
    pins: [
  { id: 3, name: 'Front Lawn', icon: '🌱', lat: 37.7748, lon: -122.4193, description: 'Main mowing area' },
  { id: 4, name: 'Back Lawn', icon: '🌳', lat: 37.7751, lon: -122.4196, description: 'Secondary area' }
    ]
  },
  {
    id: 'obstacles',
    name: 'Obstacles',
    pins: [
      { id: 5, name: 'Tree', icon: '🌲', lat: 37.7749, lon: -122.4193, description: 'Large oak tree' },
      { id: 6, name: 'Pond', icon: '🟦', lat: 37.7750, lon: -122.4195, description: 'Water feature' }
    ]
  }
])

const availableIcons = ['📍', '🏠', '🚪', '🌱', '🌳', '🌲', '🟦', '⚠️', '🔧', '⛽', '🎯', '📡']

// Computed
const previewUrl = computed(() => {
  if (settings.value.provider === 'none') return ''
  // Only attempt Google preview when we have a key
  if (settings.value.provider === 'google' && settings.value.google_api_key) {
    const baseUrl = 'https://maps.googleapis.com/maps/api/staticmap'
    const params = new URLSearchParams({
      center: `${previewLat.value},${previewLon.value}`,
      zoom: previewZoom.value.toString(),
      size: '400x300',
      maptype: settings.value.style === 'standard' ? 'roadmap' : settings.value.style,
      key: settings.value.google_api_key
    })
    return `${baseUrl}?${params}`
  }
  // For OSM or google-without-key, we skip <img> preview; the editor Leaflet map below is the live preview
  return ''
})

// Methods
async function loadSettings() {
  try {
    const response = await api.get('/api/v2/settings/maps')
    settings.value = { ...settings.value, ...response.data }
  } catch (error) {
    console.error('Failed to load map settings:', error)
    showStatus('Failed to load settings', false)
  }
}

async function saveSettings() {
  saving.value = true
  try {
    await api.put('/api/v2/settings/maps', settings.value)
    showStatus('Settings saved successfully!', true)
  } catch (error) {
    console.error('Failed to save settings:', error)
    showStatus('Failed to save settings', false)
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  apiStatus.value = null
  
  try {
    if (settings.value.provider === 'google' && settings.value.google_api_key) {
      // Prefer official JS API loader to validate the key properly
      try {
        const { Loader } = await import('@googlemaps/js-api-loader')
        const loader = new Loader({
          apiKey: settings.value.google_api_key,
          version: 'weekly'
        })
        await loader.load()
        apiStatus.value = { valid: true, message: 'Google Maps JavaScript API loaded successfully' }
      } catch (e: any) {
        // As a fallback, try loading a tiny static map image to observe HTTP status
        const params = new URLSearchParams({
          center: '37.7749,-122.4194',
          zoom: '12',
          size: '1x1',
          key: settings.value.google_api_key
        })
        const staticUrl = `https://maps.googleapis.com/maps/api/staticmap?${params}`
        const imgResp = await fetch(staticUrl, { method: 'GET', mode: 'no-cors' })
        // no-cors opaque response won't expose status; if no exception, assume network OK but key may still be invalid
        apiStatus.value = { valid: false, message: 'Failed to load JS API. Check key restrictions (HTTP referrer/IP) and enable Maps JavaScript API.' }
      }
    } else if (settings.value.provider === 'osm') {
      // Test OSM tile server
      const testUrl = 'https://tile.openstreetmap.org/1/0/0.png'
      const response = await fetch(testUrl, { method: 'GET' })
      
      if (response.ok) {
        apiStatus.value = { valid: true, message: 'OpenStreetMap tiles accessible' }
      } else {
        apiStatus.value = { valid: false, message: 'Unable to access OSM tiles' }
      }
    }
  } catch (error) {
    apiStatus.value = { valid: false, message: 'Connection test failed' }
  } finally {
    testing.value = false
  }
}

function onProviderChange() {
  apiStatus.value = null
  previewError.value = ''
}

function onPreviewError() {
  previewError.value = 'Failed to load map preview'
}

function onPreviewLoad() {
  previewError.value = ''
}

function showStatus(message: string, success: boolean) {
  statusMessage.value = message
  statusSuccess.value = success
  setTimeout(() => {
    statusMessage.value = ''
  }, 3000)
}

// Pin management
function addPin(categoryId: string) {
  editingPin.value = null
  pinForm.value = {
    name: '',
    category: categoryId,
    icon: '📍',
    lat: previewLat.value,
    lon: previewLon.value,
    description: ''
  }
  showPinEditor.value = true
}

function editPin(pin: any) {
  editingPin.value = pin
  pinForm.value = { ...pin }
  showPinEditor.value = true
}

function deletePin(pin: any) {
  if (confirm(`Delete pin "${pin.name}"?`)) {
    const category = pinCategories.value.find(cat => 
      cat.pins.some(p => p.id === pin.id)
    )
    if (category) {
      const index = category.pins.findIndex(p => p.id === pin.id)
      if (index > -1) {
        category.pins.splice(index, 1)
      }
    }
  }
}

function selectPin(pin: any) {
  selectedPin.value = pin
  previewLat.value = pin.lat
  previewLon.value = pin.lon
}

function savePin() {
  if (editingPin.value) {
    // Update existing pin
    Object.assign(editingPin.value, pinForm.value)
  } else {
    // Add new pin
    const category = pinCategories.value.find(cat => cat.id === pinForm.value.category)
    if (category) {
      const newPin = {
        ...pinForm.value,
        id: Date.now() // Simple ID generation
      }
      category.pins.push(newPin)
    }
  }
  closePinEditor()
}

function closePinEditor() {
  showPinEditor.value = false
  editingPin.value = null
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.maps-view {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
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

.form-control, .form-control-sm {
  width: 100%;
  padding: 0.75rem;
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  color: var(--text-color);
  font-size: 1rem;
}

.form-control-sm {
  padding: 0.375rem 0.5rem;
  font-size: 0.875rem;
}

.form-control:focus, .form-control-sm:focus {
  outline: none;
  border-color: var(--accent-green);
  box-shadow: 0 0 0 2px rgba(0, 255, 146, 0.2);
}

.input-group {
  display: flex;
}

.input-group .form-control {
  border-radius: 4px 0 0 4px;
}

.input-group .btn {
  border-radius: 0 4px 4px 0;
  border-left: none;
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

.provider-config {
  margin-left: 1rem;
  padding-left: 1rem;
  border-left: 3px solid var(--accent-green);
  margin-top: 1rem;
}

.api-status {
  margin-top: 1rem;
  padding: 1rem;
  border-radius: 4px;
  background: var(--primary-dark);
}

.status-indicator {
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.status-success {
  color: var(--accent-green);
}

.status-error {
  color: #ff4343;
}

.status-message {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.action-buttons {
  display: flex;
  gap: 1rem;
  margin-top: 2rem;
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

.map-preview {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.preview-controls {
  background: var(--primary-dark);
  padding: 1rem;
  border-radius: 4px;
}

.coordinate-inputs {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.coordinate-inputs label {
  margin: 0;
  white-space: nowrap;
}

.tile-preview {
  position: relative;
  text-align: center;
}

.tile-preview img {
  max-width: 100%;
  height: auto;
  border: 1px solid var(--primary-light);
  border-radius: 4px;
}

.preview-error {
  padding: 2rem;
  background: var(--primary-dark);
  border: 1px solid #ff4343;
  border-radius: 4px;
  color: #ff4343;
}

.preview-meta {
  margin-top: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.pin-categories {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.category {
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  background: var(--primary-dark);
}

.category-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--primary-light);
}

.category-header h4 {
  margin: 0;
  color: var(--accent-green);
}

.pin-list {
  padding: 1rem;
}

.pin-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.pin-item:hover {
  background: var(--secondary-dark);
}

.pin-item.active {
  background: rgba(0, 255, 146, 0.1);
  border: 1px solid var(--accent-green);
}

.pin-icon {
  font-size: 1.5rem;
  min-width: 2rem;
  text-align: center;
}

.pin-info {
  flex: 1;
}

.pin-name {
  font-weight: 500;
  color: var(--text-color);
}

.pin-coords {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.pin-actions {
  display: flex;
  gap: 0.5rem;
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
  max-width: 500px;
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

.form-row {
  display: flex;
  gap: 1rem;
}

.form-row .form-group {
  flex: 1;
}

.icon-picker {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.icon-button {
  padding: 0.5rem;
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  background: var(--primary-dark);
  color: var(--text-color);
  cursor: pointer;
  font-size: 1.25rem;
  transition: all 0.3s ease;
}

.icon-button:hover {
  background: var(--secondary-dark);
}

.icon-button.active {
  border-color: var(--accent-green);
  background: rgba(0, 255, 146, 0.1);
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
  .coordinate-inputs {
    flex-direction: column;
    align-items: stretch;
  }
  
  .action-buttons {
    flex-direction: column;
  }
  
  .category-header {
    flex-direction: column;
    gap: 1rem;
    align-items: stretch;
  }
}
</style>
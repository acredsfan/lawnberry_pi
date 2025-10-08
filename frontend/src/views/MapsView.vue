<template>
  <div class="maps-view">
    <div class="page-header">
      <h1>Map Editor</h1>
      <p class="text-muted">Edit boundary, zones, and waypoints; view coverage and mower location</p>
    </div>

    <!-- Provider configuration and preview moved to Settings; retained settings load to drive editor tiles. -->

    <!-- Boundary & Zone Editor -->
    <div v-if="settings.provider !== 'none'" class="card">
      <div class="card-header">
        <h3>Boundary & Zone Editor</h3>
      </div>
      <div class="card-body" style="height: 720px;">
        <BoundaryEditor
          ref="editorRef"
          :map-provider="settings.provider === 'google' ? 'google' : (settings.provider === 'osm' ? 'osm' : 'none')"
          :map-style="settings.style"
          :google-api-key="settings.google_api_key"
          :pick-for-pin="pickForPin"
          @pinPicked="onPinPicked"
        />
      </div>
    </div>

    <!-- Pin & Zone Asset Management -->
    <div class="card">
      <div class="card-header">
        <h3>Pins & Zones</h3>
      </div>
      <div class="card-body">
        <div class="pin-categories">
          <!-- Waypoints / Markers -->
          <div class="category">
            <div class="category-header">
              <h4>Waypoints</h4>
              <div style="display:flex; gap:.5rem">
                <button class="btn btn-sm btn-primary" @click="addPin('waypoints')">Add Pin</button>
              </div>
            </div>
            <div class="pin-list">
              <div 
                v-for="m in (mapStore.configuration?.markers || [])" 
                :key="m.marker_id"
                class="pin-item"
                :class="{ active: selectedPinId === m.marker_id }"
                @click="selectMarker(m)"
              >
                <div class="pin-icon">{{ iconForMarker(m.marker_type) }}</div>
                <div class="pin-info">
                  <div class="pin-name">{{ m.label || m.marker_type }}</div>
                  <div class="pin-coords">{{ m.position.latitude.toFixed(6) }}, {{ m.position.longitude.toFixed(6) }}</div>
                </div>
                <div class="pin-actions">
                  <button class="btn btn-xs btn-secondary" @click.stop="editMarker(m)">✏️</button>
                  <button class="btn btn-xs btn-info" @click.stop="editMarkerOnMap(m)">🗺️ Edit on map</button>
                  <button class="btn btn-xs btn-danger" @click.stop="deleteMarker(m)">🗑️</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Mowing Zones -->
          <div class="category">
            <div class="category-header">
              <h4>Mowing Zones</h4>
            </div>
            <div class="pin-list">
              <div 
                v-for="z in (mapStore.configuration?.mowing_zones || [])" 
                :key="z.id"
                class="pin-item"
              >
                <div class="pin-icon">🌱</div>
                <div class="pin-info">
                  <div class="pin-name">{{ z.name }}</div>
                  <div class="pin-coords">{{ z.polygon.length }} points</div>
                </div>
                <div class="pin-actions">
                  <button class="btn btn-xs btn-secondary" @click.stop="renameZone(z)">✏️</button>
                  <button class="btn btn-xs btn-info" @click.stop="editZoneOnMap(z)">🗺️ Edit on map</button>
                  <button class="btn btn-xs btn-danger" @click.stop="removeMow(z)">🗑️</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Exclusion Zones -->
          <div class="category">
            <div class="category-header">
              <h4>Exclusion Zones</h4>
            </div>
            <div class="pin-list">
              <div 
                v-for="z in (mapStore.configuration?.exclusion_zones || [])" 
                :key="z.id"
                class="pin-item"
              >
                <div class="pin-icon">🚫</div>
                <div class="pin-info">
                  <div class="pin-name">{{ z.name }}</div>
                  <div class="pin-coords">{{ z.polygon.length }} points</div>
                </div>
                <div class="pin-actions">
                  <button class="btn btn-xs btn-secondary" @click.stop="renameZone(z)">✏️</button>
                  <button class="btn btn-xs btn-info" @click.stop="editExclusionOnMap(z)">🗺️ Edit on map</button>
                  <button class="btn btn-xs btn-danger" @click.stop="removeExclusion(z)">🗑️</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Boundary quick-edit -->
          <div class="category">
            <div class="category-header">
              <h4>Boundary</h4>
              <div style="display:flex; gap:.5rem">
                <button class="btn btn-sm btn-info" @click="editBoundaryOnMap">🗺️ Edit boundary on map</button>
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
            <button class="btn btn-secondary" type="button" @click="enablePickOnMap">
              📍 Pick location on map
            </button>
            <span v-if="pickForPin" style="margin-left: .5rem; color: var(--accent-green);">Click on the map…</span>
          </div>
          
          <div class="form-group">
            <label>Description</label>
            <textarea v-model="pinForm.description" class="form-control" rows="3" />
            <small class="form-text text-muted">Note: This mower uses solar charging; no dock is required. Use AM/PM Sun spots for optimal charging behavior.</small>
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
import { useMapStore } from '@/stores/map'
import { useToastStore } from '@/stores/toast'

const api = useApiService()
const mapStore = useMapStore()
const toast = useToastStore()
const editorRef = ref<any>(null)

// State
const settings = ref({
  provider: 'osm',
  google_api_key: '',
  google_billing_warnings: true,
  style: 'standard'
})

const showApiKey = ref(false)
const apiStatus = ref<{valid: boolean, message?: string} | null>(null)

// Preview state
const previewLat = ref(37.7749)
const previewLon = ref(-122.4194)
const previewZoom = ref(15)
const previewError = ref('')

// Pin management state (for add/edit)
const showPinEditor = ref(false)
const editingMarkerId = ref<string | null>(null)
const selectedPinId = ref<string | null>(null)
const pinForm = ref({
  name: '',
  type: 'custom',
  icon: '📍',
  lat: 0,
  lon: 0,
  description: ''
})

// Pin pick-from-map state
const pickForPin = ref(false)
let reopenAfterPick = false

const availableIcons = ['📍', '🏠', '☀️', '🌅', '🚪', '🌱', '🌳', '🌲', '🟦', '⚠️', '🔧', '⛽', '🎯', '📡']

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
    toast.show('Map settings loaded', 'info', 2000)
  } catch (error) {
    console.error('Failed to load map settings:', error)
    showStatus('Failed to load settings', false)
    toast.show('Failed to load map settings', 'error')
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

function showStatus(_message: string, _success: boolean) {}

// Pin management
function addPin(_categoryId: string) {
  editingMarkerId.value = null
  pinForm.value = {
    name: '',
    type: 'custom',
    icon: '📍',
    lat: previewLat.value,
    lon: previewLon.value,
    description: ''
  }
  showPinEditor.value = true
}

function editMarker(m: any) {
  editingMarkerId.value = m.marker_id
  pinForm.value = { name: m.label || '', type: m.marker_type, icon: iconForMarker(m.marker_type), lat: m.position.latitude, lon: m.position.longitude, description: '' }
  showPinEditor.value = true
}

async function deleteMarker(m: any) {
  if (!confirm(`Delete marker "${m.label || m.marker_type}"?`)) return
  try {
    mapStore.removeMarker(m.marker_id)
    await mapStore.saveConfiguration()
    toast.show('Marker removed', 'success', 1500)
  } catch (error) {
    console.error(error)
    toast.show('Failed to delete marker', 'error')
  }
}

function selectMarker(m: any) {
  selectedPinId.value = m.marker_id
  previewLat.value = m.position.latitude
  previewLon.value = m.position.longitude
}

async function savePin() {
  try {
    if (editingMarkerId.value) {
      mapStore.updateMarker(editingMarkerId.value, {
        label: pinForm.value.name || undefined,
        marker_type: pinForm.value.type,
        position: { latitude: pinForm.value.lat, longitude: pinForm.value.lon }
      } as any)
    } else {
      mapStore.addMarker(pinForm.value.type as any, { latitude: pinForm.value.lat, longitude: pinForm.value.lon }, pinForm.value.name)
    }
    await mapStore.saveConfiguration()
    toast.show('Marker saved', 'success', 1800)
  } catch (e) {
    console.error(e)
    toast.show('Failed to save marker', 'error')
  }
  closePinEditor()
}

function closePinEditor() {
  showPinEditor.value = false
  editingMarkerId.value = null
  pickForPin.value = false
}

onMounted(() => {
  loadSettings()
})

function enablePickOnMap() {
  // Hide the modal so map clicks are not blocked
  reopenAfterPick = true
  showPinEditor.value = false
  // Slight delay to allow modal transition (if any)
  setTimeout(() => { pickForPin.value = true }, 50)
}

function onPinPicked(coords: { latitude: number; longitude: number }) {
  // Reopen editor if we initiated pick from modal
  if (reopenAfterPick) {
    showPinEditor.value = true
    reopenAfterPick = false
  }
  pinForm.value.lat = coords.latitude
  pinForm.value.lon = coords.longitude
  pickForPin.value = false
}

// Apply the current Pin modal coordinates to the live configuration as a marker
const applyMarkerType = ref<'home'|'am_sun'|'pm_sun'|'custom'>('home')
async function applyPinToConfiguration() {
  try {
    if (!mapStore.configuration) {
      await mapStore.loadConfiguration('default')
    }
    mapStore.addMarker(applyMarkerType.value, { latitude: pinForm.value.lat, longitude: pinForm.value.lon })
    await mapStore.saveConfiguration()
    showStatus('Marker applied to configuration', true)
  } catch (e) {
    showStatus('Failed to apply marker', false)
  }
}

// Quick actions: Add polygon zones via the map editor
function addMowingZoneOnMap() {
  mapStore.setEditMode('mowing')
}
function addExclusionZoneOnMap() {
  mapStore.setEditMode('exclusion')
}

function iconForMarker(type: string) {
  return type === 'home' ? '🏠' : type === 'am_sun' ? '☀️' : type === 'pm_sun' ? '🌅' : '📍'
}

async function removeMow(z: any) {
  if (!confirm(`Delete mowing zone "${z.name}"?`)) return
  try {
    mapStore.removeMowingZone(z.id)
    await mapStore.saveConfiguration()
    toast.show('Mowing zone removed', 'success', 1500)
  } catch (error) {
    console.error(error)
    toast.show('Failed to delete mowing zone', 'error')
  }
}

async function renameZone(z: any) {
  const name = prompt('Zone name', z.name)
  if (!name) return
  mapStore.updateZoneName(z.id, name)
  try {
    await mapStore.saveConfiguration()
    toast.show('Zone renamed', 'success', 1500)
  } catch (error) {
    console.error(error)
    toast.show('Failed to rename zone', 'error')
  }
}

async function removeExclusion(z: any) {
  if (!confirm(`Delete exclusion zone "${z.name}"?`)) return
  try {
    mapStore.removeExclusionZone(z.id)
    await mapStore.saveConfiguration()
    toast.show('Exclusion zone removed', 'success', 1500)
  } catch (error) {
    console.error(error)
    toast.show('Failed to delete exclusion zone', 'error')
  }
}

function editMarkerOnMap(m: any) {
  try { editorRef.value?.focusMarker(m.marker_id) } catch {}
}

function editZoneOnMap(z: any) {
  try { editorRef.value?.editZoneOnMap(z.id, 'mowing') } catch {}
}

function editExclusionOnMap(z: any) {
  try { editorRef.value?.editZoneOnMap(z.id, 'exclusion') } catch {}
}

function editBoundaryOnMap() {
  try { editorRef.value?.editZoneOnMap('', 'boundary') } catch {}
}
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
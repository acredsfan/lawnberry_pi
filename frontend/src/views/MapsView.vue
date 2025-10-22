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
                :class="{ active: selectedPinId === m.marker_id, home: m.marker_type === 'home' || m.is_home }"
                @click="selectMarker(m)"
              >
                <div class="pin-icon">{{ m.icon || iconForMarker(m.marker_type) }}</div>
                <div class="pin-info">
                  <div class="pin-name">
                    {{ displayMarkerName(m) }}
                    <span v-if="m.marker_type === 'home' || m.is_home" class="pin-badge">Home</span>
                  </div>
                  <div class="pin-coords">{{ m.position.latitude.toFixed(6) }}, {{ m.position.longitude.toFixed(6) }}</div>
                  <div v-if="summarizeSchedule(m)" class="pin-schedule">{{ summarizeSchedule(m) }}</div>
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
            <label>Pin Type</label>
            <select v-model="pinForm.type" class="form-control" :disabled="pinForm.isHome">
              <option value="custom">Custom</option>
              <option value="am_sun">AM Sun</option>
              <option value="pm_sun">PM Sun</option>
            </select>
            <small v-if="!pinForm.isHome" class="form-text text-muted">Type helps categorize scheduled visits.</small>
          </div>

          <div class="form-group form-switch">
            <label class="toggle-label">
              <input type="checkbox" v-model="pinForm.isHome">
              Designate as home location
            </label>
            <small class="form-text text-muted">Home is the default return spot when other conditions are not met.</small>
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

          <fieldset class="schedule-fieldset" :disabled="pinForm.isHome">
            <legend>Conditions &amp; Triggers</legend>
            <div class="form-group">
              <label>Time Windows</label>
              <div
                class="time-window-row"
                v-for="(window, idx) in pinForm.schedule.windows"
                :key="`tw-${idx}`"
              >
                <input type="time" class="form-control-sm" v-model="window.start">
                <span>to</span>
                <input type="time" class="form-control-sm" v-model="window.end">
                <button
                  v-if="pinForm.schedule.windows.length > 1"
                  class="btn btn-xs btn-danger"
                  type="button"
                  @click="removeTimeWindow(pinForm.schedule, idx)"
                >
                  ✖️
                </button>
              </div>
              <button class="btn btn-xs btn-secondary" type="button" @click="addTimeWindow(pinForm.schedule)">
                ➕ Add window
              </button>
            </div>

            <div class="form-group">
              <label>Days of Week</label>
              <div class="day-toggle-row">
                <button
                  v-for="day in daysOfWeek"
                  :key="day.value"
                  type="button"
                  class="day-toggle"
                  :class="{ active: isDaySelected(pinForm.schedule, day.value) }"
                  @click="toggleDay(pinForm.schedule, day.value)"
                >
                  {{ day.short }}
                </button>
              </div>
            </div>

            <div class="form-group">
              <label>Triggers</label>
              <label class="form-check-inline">
                <input type="checkbox" v-model="pinForm.schedule.triggers.needs_charge">
                Needs charge
              </label>
              <label class="form-check-inline">
                <input type="checkbox" v-model="pinForm.schedule.triggers.precipitation">
                Dry weather
              </label>
              <label class="form-check-inline">
                <input type="checkbox" v-model="pinForm.schedule.triggers.manual_override">
                Manual
              </label>
            </div>
          </fieldset>

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

    <div
      v-if="isE2ETestMode"
      class="card test-harness-card"
      data-testid="e2e-map-tools"
    >
      <div class="card-header">
        <h3>E2E Test Harness</h3>
      </div>
      <div class="card-body">
        <p class="text-muted">Synthetic helpers for automated Playwright scenarios.</p>
        <div class="test-button-row">
          <button
            class="btn btn-sm btn-primary"
            type="button"
            data-testid="e2e-add-mowing-zone"
            @click="addSyntheticMowingZone"
          >
            ➕ Add synthetic mowing zone
          </button>
          <button
            class="btn btn-sm btn-secondary"
            type="button"
            data-testid="e2e-save-map"
            @click="saveConfigurationForTest"
          >
            💾 Save configuration
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useApiService } from '@/services/api'
import BoundaryEditor from '@/components/map/BoundaryEditor.vue'
import { useMapStore } from '@/stores/map'
import { useToastStore } from '@/stores/toast'
import type { MarkerSchedule } from '@/stores/map'

const api = useApiService()
const mapStore = useMapStore()
const toast = useToastStore()
const editorRef = ref<any>(null)
const isE2ETestMode = computed(() => typeof window !== 'undefined' && (window.location.search.includes('e2e=1') || window.location.search.includes('e2e=true')))

// State
const settings = ref({
  provider: 'osm',
  google_api_key: '',
  google_billing_warnings: true,
  style: 'standard'
})

type ScheduleForm = {
  windows: Array<{ start: string; end: string }>
  days: number[]
  triggers: {
    needs_charge: boolean
    precipitation: boolean
    manual_override: boolean
  }
}

const defaultScheduleForm = (): ScheduleForm => ({
  windows: [{ start: '08:00', end: '10:00' }],
  days: [],
  triggers: {
    needs_charge: false,
    precipitation: false,
    manual_override: false
  }
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
  description: '',
  isHome: false,
  schedule: defaultScheduleForm()
})

// Pin pick-from-map state
const pickForPin = ref(false)
let reopenAfterPick = false

const availableIcons = ['📍', '🏠', '☀️', '🌅', '🚪', '🌱', '🌳', '🌲', '🟦', '⚠️', '🔧', '⛽', '🎯', '📡']

const statusMessage = ref('')
const statusSuccess = ref(true)
const statusTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const daysOfWeek = [
  { value: 0, label: 'Sunday', short: 'Su' },
  { value: 1, label: 'Monday', short: 'Mo' },
  { value: 2, label: 'Tuesday', short: 'Tu' },
  { value: 3, label: 'Wednesday', short: 'We' },
  { value: 4, label: 'Thursday', short: 'Th' },
  { value: 5, label: 'Friday', short: 'Fr' },
  { value: 6, label: 'Saturday', short: 'Sa' }
]

function toMarkerSchedule(form: ScheduleForm): MarkerSchedule | null {
  const windows = form.windows
    .filter(w => w.start && w.end)
    .map(w => ({ start: w.start, end: w.end }))
  const days = Array.from(new Set(form.days)).filter(d => d >= 0 && d <= 6).sort((a, b) => a - b)
  const triggers = {
    needs_charge: Boolean(form.triggers.needs_charge),
    precipitation: Boolean(form.triggers.precipitation),
    manual_override: Boolean(form.triggers.manual_override)
  }
  if (!windows.length && !days.length && !triggers.needs_charge && !triggers.precipitation && !triggers.manual_override) {
    return null
  }
  return {
    time_windows: windows,
    days_of_week: days,
    triggers
  }
}

function scheduleFormFromMarker(marker: any): ScheduleForm {
  const schedule: MarkerSchedule | undefined = marker?.schedule || marker?.metadata?.schedule || null
  if (!schedule) {
    return defaultScheduleForm()
  }
  const windows = Array.isArray(schedule.time_windows) && schedule.time_windows.length
    ? schedule.time_windows.map((w: any) => ({ start: w?.start || '', end: w?.end || '' }))
    : [{ start: '08:00', end: '10:00' }]
  const days = Array.isArray(schedule.days_of_week) ? [...schedule.days_of_week] : []
  const triggers = {
    needs_charge: Boolean(schedule.triggers?.needs_charge),
    precipitation: Boolean(schedule.triggers?.precipitation),
    manual_override: Boolean(schedule.triggers?.manual_override)
  }
  return {
    windows,
    days,
    triggers
  }
}

function addTimeWindow(target: ScheduleForm) {
  target.windows.push({ start: '08:00', end: '10:00' })
}

function removeTimeWindow(target: ScheduleForm, idx: number) {
  if (target.windows.length <= 1) {
    target.windows[0] = { start: '08:00', end: '10:00' }
    return
  }
  target.windows.splice(idx, 1)
}

function toggleDay(target: ScheduleForm, dayValue: number) {
  const pos = target.days.indexOf(dayValue)
  if (pos === -1) {
    target.days.push(dayValue)
  } else {
    target.days.splice(pos, 1)
  }
}

function isDaySelected(target: ScheduleForm, dayValue: number): boolean {
  return target.days.includes(dayValue)
}

function summarizeSchedule(marker: any): string | null {
  const schedule: MarkerSchedule | undefined = marker?.schedule || marker?.metadata?.schedule
  if (!schedule) {
    return null
  }
  const parts: string[] = []
  if (Array.isArray(schedule.days_of_week) && schedule.days_of_week.length) {
    const dayLbl = schedule.days_of_week
      .map((d: number) => daysOfWeek.find(day => day.value === d)?.short || '')
      .filter(Boolean)
      .join(' ')
    if (dayLbl) parts.push(dayLbl)
  }
  if (Array.isArray(schedule.time_windows) && schedule.time_windows.length) {
    const winLbl = schedule.time_windows
      .map((w: any) => `${w.start ?? ''}-${w.end ?? ''}`.trim())
      .filter(Boolean)
      .join(', ')
    if (winLbl) parts.push(winLbl)
  }
  const triggerParts: string[] = []
  if (schedule.triggers?.needs_charge) triggerParts.push('needs charge')
  if (schedule.triggers?.precipitation) triggerParts.push('dry weather')
  if (schedule.triggers?.manual_override) triggerParts.push('manual')
  if (triggerParts.length) parts.push(triggerParts.join(', '))
  return parts.length ? parts.join(' • ') : null
}

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
    const response = await api.get('/api/v2/settings/maps', { headers: { 'Cache-Control': 'no-cache' } })
    const payload = response?.data && typeof response.data === 'object' ? response.data : {}
    settings.value = { ...settings.value, ...payload }
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

function showStatus(message: string, success: boolean) {
  statusMessage.value = message
  statusSuccess.value = success
  if (statusTimer.value) {
    clearTimeout(statusTimer.value)
  }
  statusTimer.value = setTimeout(() => {
    statusMessage.value = ''
    statusTimer.value = null
  }, 3000)
}

// Pin management
function addPin(_categoryId: string) {
  editingMarkerId.value = null
  pinForm.value = {
    name: '',
    type: 'custom',
    icon: '📍',
    lat: previewLat.value,
    lon: previewLon.value,
    description: '',
    isHome: false,
    schedule: defaultScheduleForm()
  }
  showPinEditor.value = true
}

function editMarker(m: any) {
  editingMarkerId.value = m.marker_id
  const isHome = m.marker_type === 'home' || m.is_home
  const baseType = ['custom', 'am_sun', 'pm_sun'].includes(m.marker_type) ? m.marker_type : 'custom'
  pinForm.value = {
    name: m.label || '',
    type: isHome ? 'custom' : baseType,
    icon: m.icon || iconForMarker(m.marker_type),
    lat: m.position.latitude,
    lon: m.position.longitude,
    description: m.metadata?.description || '',
    isHome,
    schedule: isHome ? defaultScheduleForm() : scheduleFormFromMarker(m)
  }
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
    const schedule = pinForm.value.isHome ? null : toMarkerSchedule(pinForm.value.schedule)
    const metadata: Record<string, any> = {}
    if (pinForm.value.description) {
      metadata.description = pinForm.value.description
    }
    if (schedule) {
      metadata.schedule = schedule
    }
    if (pinForm.value.isHome) {
      metadata.is_home = true
    }
    const markerType = pinForm.value.isHome ? 'home' : (pinForm.value.type as any)
    const label = pinForm.value.name || undefined
    if (editingMarkerId.value) {
      mapStore.updateMarker(editingMarkerId.value, {
        label,
        marker_type: markerType,
        position: { latitude: pinForm.value.lat, longitude: pinForm.value.lon },
        icon: pinForm.value.icon,
        metadata,
        schedule,
        is_home: pinForm.value.isHome
      })
    } else {
      mapStore.addMarker(
        markerType,
        { latitude: pinForm.value.lat, longitude: pinForm.value.lon },
        {
          label,
          icon: pinForm.value.icon,
          metadata,
          schedule,
          isHome: pinForm.value.isHome
        }
      )
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
  pinForm.value = {
    name: '',
    type: 'custom',
    icon: '📍',
    lat: previewLat.value,
    lon: previewLon.value,
    description: '',
    isHome: false,
    schedule: defaultScheduleForm()
  }
}

onMounted(async () => {
  await loadSettings()
  try {
    if (!mapStore.configuration) {
      await mapStore.loadConfiguration('default')
    }
  } catch (error) {
    console.error('Failed to load map configuration:', error)
    showStatus('Failed to load map configuration', false)
    toast.show('Failed to load map configuration', 'error')
  }
})

onUnmounted(() => {
  if (statusTimer.value) {
    clearTimeout(statusTimer.value)
    statusTimer.value = null
  }
})

watch(() => pinForm.value.isHome, (isHome) => {
  if (isHome) {
    pinForm.value.schedule = defaultScheduleForm()
  }
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
    const schedule = applyMarkerType.value === 'home' ? null : toMarkerSchedule(pinForm.value.schedule)
    const metadata = schedule
      ? { schedule: { ...schedule, time_windows: schedule.time_windows.map(w => ({ ...w })) } }
      : undefined
    mapStore.addMarker(
      applyMarkerType.value,
      { latitude: pinForm.value.lat, longitude: pinForm.value.lon },
      {
        label: pinForm.value.name || undefined,
        metadata,
        schedule,
        isHome: applyMarkerType.value === 'home'
      }
    )
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

function addSyntheticMowingZone() {
  if (!mapStore.configuration) return
  const zoneId = `test-zone-${Date.now().toString(36)}`
  const baseLat = 37.7749
  const baseLon = -122.4194
  const polygon = [
    { latitude: baseLat, longitude: baseLon },
    { latitude: baseLat + 0.0009, longitude: baseLon },
    { latitude: baseLat + 0.0009, longitude: baseLon + 0.0012 },
    { latitude: baseLat, longitude: baseLon + 0.0012 },
  ]
  mapStore.addMowingZone({
    id: zoneId,
    name: `Test Zone ${mapStore.configuration.mowing_zones.length + 1}`,
    zone_type: 'mow',
    polygon,
  })
  showStatus('Synthetic mowing zone added', true)
}

async function saveConfigurationForTest() {
  try {
    await mapStore.saveConfiguration()
    showStatus('Configuration saved for test', true)
  } catch (error) {
    console.error('Failed to save configuration in test harness', error)
    showStatus('Failed to save configuration', false)
  }
}

function displayMarkerName(marker: any) {
  if (marker?.label) return marker.label
  const type = String(marker?.marker_type || '')
  if (type === 'home') return 'Home'
  if (!type) return 'Pin'
  return type.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
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

.form-switch {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: var(--text-color);
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

.pin-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.4rem;
  margin-left: 0.5rem;
  border-radius: 999px;
  background: rgba(0, 255, 146, 0.15);
  color: var(--accent-green);
  font-size: 0.75rem;
  font-weight: 600;
}

.pin-coords {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.pin-schedule {
  margin-top: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.pin-item.home {
  border-left: 3px solid var(--accent-green);
}

.pin-item.home .pin-icon {
  transform: scale(1.05);
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

.schedule-fieldset {
  border: 1px solid var(--primary-light);
  border-radius: 6px;
  padding: 1rem;
  margin-bottom: 1.5rem;
}

.schedule-fieldset legend {
  padding: 0 0.5rem;
  font-size: 0.95rem;
  color: var(--accent-green);
}

.time-window-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.day-toggle-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.day-toggle {
  padding: 0.35rem 0.6rem;
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  background: var(--primary-dark);
  color: var(--text-color);
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.day-toggle.active {
  background: rgba(0, 255, 146, 0.15);
  border-color: var(--accent-green);
  color: var(--accent-green);
}

.form-check-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-right: 1rem;
  color: var(--text-color);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid var(--primary-light);
}

.test-harness-card {
  margin-top: 1.5rem;
}

.test-button-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
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
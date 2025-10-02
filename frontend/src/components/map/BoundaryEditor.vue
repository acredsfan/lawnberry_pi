<template>
  <div class="boundary-editor">
    <div class="editor-toolbar">
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'view', 'btn-secondary': mode !== 'view' }"
        @click="setMode('view')"
      >
        👁️ View
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'boundary', 'btn-secondary': mode !== 'boundary' }"
        @click="setMode('boundary')"
      >
        📍 Boundary
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'exclusion', 'btn-secondary': mode !== 'exclusion' }"
        @click="setMode('exclusion')"
      >
        🚫 Exclusion
      </button>
      <button 
        class="btn btn-sm" 
        :class="{ 'btn-primary': mode === 'marker', 'btn-secondary': mode !== 'marker' }"
        @click="setMode('marker')"
      >
        📌 Marker
      </button>
      
      <div class="toolbar-spacer"></div>
      
      <button 
        v-if="hasUnsavedChanges" 
        class="btn btn-sm btn-success"
        @click="saveChanges"
      >
        💾 Save
      </button>
      <button 
        v-if="currentPolygon.length > 0" 
        class="btn btn-sm btn-warning"
        @click="clearCurrent"
      >
        🗑️ Clear
      </button>
    </div>

    <div class="editor-canvas" ref="canvasContainer">
      <div v-if="mode === 'boundary'" class="editor-instructions">
        Click on the map to add boundary points. Close the polygon by clicking near the first point.
      </div>
      <div v-if="mode === 'exclusion'" class="editor-instructions">
        Click on the map to add exclusion zone points. Close the polygon by clicking near the first point.
      </div>
      <div v-if="mode === 'marker'" class="editor-instructions">
        Click on the map to place a marker.
        <select v-model="markerType" class="marker-type-select">
          <option value="home">🏠 Home</option>
          <option value="am_sun">☀️ AM Sun</option>
          <option value="pm_sun">🌅 PM Sun</option>
          <option value="custom">📍 Custom</option>
        </select>
      </div>

      <!-- Map rendering would go here -->
      <div class="map-placeholder">
        <div class="placeholder-text">
          Map component (Google Maps/Leaflet integration)
        </div>
        <div v-if="currentPolygon.length > 0" class="current-points">
          <strong>Current points:</strong> {{ currentPolygon.length }}
        </div>
      </div>
    </div>

    <div class="editor-status">
      <div v-if="error" class="alert alert-danger">
        {{ error }}
      </div>
      <div v-if="successMessage" class="alert alert-success">
        {{ successMessage }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useMapStore } from '../../stores/map';
import type { Point } from '../../stores/map';

const mapStore = useMapStore();

// Props
interface Props {
  configId?: string;
}

const props = withDefaults(defineProps<Props>(), {
  configId: 'default'
});

// State
const mode = computed(() => mapStore.editMode);
const currentPolygon = ref<Point[]>([]);
const markerType = ref<'home' | 'am_sun' | 'pm_sun' | 'custom'>('home');
const hasUnsavedChanges = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);

// Methods
function setMode(newMode: 'view' | 'boundary' | 'exclusion' | 'marker') {
  mapStore.setEditMode(newMode);
  currentPolygon.value = [];
}

function clearCurrent() {
  currentPolygon.value = [];
  hasUnsavedChanges.value = false;
}

async function saveChanges() {
  error.value = null;
  successMessage.value = null;
  
  try {
    if (mode.value === 'boundary' && currentPolygon.value.length >= 3) {
      mapStore.setBoundaryZone({
        id: `boundary_${Date.now()}`,
        name: 'Mowing Boundary',
        zone_type: 'boundary',
        polygon: currentPolygon.value,
        priority: 10,
        enabled: true
      });
    } else if (mode.value === 'exclusion' && currentPolygon.value.length >= 3) {
      mapStore.addExclusionZone({
        id: `exclusion_${Date.now()}`,
        name: 'Exclusion Zone',
        zone_type: 'exclusion_zone',
        polygon: currentPolygon.value,
        priority: 5,
        enabled: true,
        exclusion_zone: true
      });
    }
    
    await mapStore.saveConfiguration();
    
    successMessage.value = 'Changes saved successfully';
    hasUnsavedChanges.value = false;
    currentPolygon.value = [];
    
    setTimeout(() => {
      successMessage.value = null;
    }, 3000);
  } catch (e: any) {
    error.value = mapStore.error || e?.message || 'Failed to save changes';
  }
}

// Emit events
const emit = defineEmits<{
  (e: 'modeChanged', mode: string): void;
  (e: 'saved'): void;
}>();

function emitModeChange() {
  emit('modeChanged', mode.value);
}
</script>

<style scoped>
.boundary-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-toolbar {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  background: var(--secondary-dark);
  border-bottom: 1px solid var(--primary-light);
}

.toolbar-spacer {
  flex: 1;
}

.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-sm {
  font-size: 0.875rem;
  padding: 0.375rem 0.75rem;
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

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
  opacity: 0.9;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.editor-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.editor-instructions {
  position: absolute;
  top: 1rem;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: var(--accent-green);
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  z-index: 100;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.marker-type-select {
  padding: 0.25rem 0.5rem;
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  color: var(--text-color);
}

.map-placeholder {
  width: 100%;
  height: 100%;
  background: var(--primary-dark);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--primary-light);
}

.placeholder-text {
  font-size: 1.25rem;
  color: var(--text-muted);
  margin-bottom: 1rem;
}

.current-points {
  color: var(--accent-green);
  font-size: 0.875rem;
}

.editor-status {
  padding: 1rem;
  min-height: 60px;
}

.alert {
  padding: 0.75rem 1rem;
  border-radius: 4px;
  margin: 0;
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
</style>

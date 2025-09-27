<template>
  <div class="maps-view">
    <div class="page-header">
      <h1>Maps</h1>
      <p class="text-muted">Map management and navigation</p>
    </div>

    <div class="card">
      <div class="card-header"><strong>Map Provider</strong></div>
      <div class="card-body">
        <div class="controls">
          <label>
            <input type="checkbox" :checked="isOffline" @change="onToggleOffline">
            Use offline mode (no API key)
          </label>
          <div class="provider">{{ providerName }}</div>
          <div class="attribution">{{ attribution }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><strong>Tile Preview</strong></div>
      <div class="card-body">
        <div class="tile-preview">
          <img :src="previewUrl" alt="Tile preview">
          <div class="meta">z={{ zoom }}, lat={{ lat.toFixed(4) }}, lon={{ lon.toFixed(4) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useOfflineMaps } from '@/composables/useOfflineMaps'

const { isOffline, setOffline, providerName, attribution, tileUrlFor } = useOfflineMaps()

const zoom = ref(15)
// Default preview: coordinates roughly around a city center (adjust as needed)
const lat = ref(37.7749)
const lon = ref(-122.4194)

const previewUrl = computed(() => tileUrlFor(lat.value, lon.value, zoom.value))

function onToggleOffline(e: Event) {
  const target = e.target as HTMLInputElement
  setOffline(target.checked)
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
  border: 1px solid #2c3e50;
  border-radius: 8px;
  background: #0b111b;
  margin-bottom: 1rem;
}

.card-header { padding: 0.75rem 1rem; border-bottom: 1px solid #2c3e50; }
.card-body { padding: 1rem; }

.controls { display: flex; flex-direction: column; gap: 0.5rem; }
.provider { font-weight: 600; }
.attribution { color: #9aa4b2; font-size: 0.85rem; }

.tile-preview { display: inline-flex; flex-direction: column; gap: 0.25rem; }
.tile-preview img { width: 256px; height: 256px; border: 1px solid #2c3e50; }
.tile-preview .meta { color: #9aa4b2; font-size: 0.85rem; }
</style>
<!-- src/components/control/CameraPanel.vue -->
<template>
  <div class="card camera-card">
    <div class="card-header"><h3>Live Camera Feed</h3></div>
    <div class="card-body">
      <div class="camera-feed" :class="{ 'camera-feed-error': cameraError }">
        <img
          v-if="cameraDisplaySource"
          :src="cameraDisplaySource"
          alt="Live mower camera feed"
          class="camera-frame"
          :class="{ 'camera-frame--stream': cameraIsStreaming }"
          @load="$emit('stream-load')"
          @error="$emit('stream-error')"
        />
        <div v-else class="camera-placeholder">
          <p>{{ cameraStatusMessage }}</p>
          <button v-if="cameraError" class="btn btn-sm btn-secondary" @click="$emit('retry')">
            Retry
          </button>
        </div>
        <div class="camera-badge" :class="`camera-badge--${cameraModeBadge?.tone ?? 'muted'}`">
          {{ cameraModeBadge?.label ?? '' }}
        </div>
      </div>
      <div class="camera-meta">
        <span :class="{ 'camera-meta-active': cameraInfo.active }">
          {{ cameraIsStreaming ? 'Streaming' : (cameraInfo.active ? 'Snapshots' : 'Idle') }}
        </span>
        <span v-if="cameraStreamUnavailable" class="camera-meta-warning">Primary MJPEG stream unavailable</span>
        <span>FPS: {{ formatFps(cameraInfo.fps) }}</span>
        <span>Last frame: {{ formatTimestamp(cameraLastFrame) }}</span>
        <span>Clients: {{ cameraInfo.client_count ?? '0' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CameraStatusSummary } from '@/composables/useCameraFeed'

defineProps<{
  cameraInfo: CameraStatusSummary
  cameraDisplaySource: string | null
  cameraIsStreaming: boolean
  cameraStreamUnavailable: boolean
  cameraStatusMessage: string
  cameraError: string | null
  cameraLastFrame: string | null
  cameraModeBadge: { label: string; tone: string }
}>()

defineEmits<{
  (e: 'stream-load'): void
  (e: 'stream-error'): void
  (e: 'retry'): void
}>()

function formatFps(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value) || value <= 0) return '—'
  return value.toFixed(1)
}

function formatTimestamp(timestamp: string | null | undefined) {
  if (!timestamp) return 'No frames yet'
  const parsed = new Date(timestamp)
  if (Number.isNaN(parsed.getTime())) return 'No frames yet'
  return parsed.toLocaleTimeString()
}
</script>

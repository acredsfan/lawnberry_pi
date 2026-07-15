<template>
  <div class="ai-view">
    <header class="page-header">
      <div>
        <h1>AI Perception</h1>
        <p class="text-muted">
          Live object detections, model provenance, freshness, and navigation cost influence.
        </p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" :disabled="loading" @click="refresh">
          {{ loading ? 'Refreshing…' : 'Refresh' }}
        </button>
        <button
          class="btn btn-primary"
          data-testid="ai-run-latest"
          :disabled="!canRequestInference || runningInference"
          @click="runLatestInference"
        >
          {{ runningInference ? 'Analyzing…' : 'Analyze latest frame' }}
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="alert alert-danger" role="alert">
      {{ errorMessage }}
    </div>

    <div v-if="status && !status.model_ready" class="alert alert-warning" role="status">
      Detector unavailable.
      {{ status.last_error || 'No validated model runtime is ready.' }} Configure
      <code>config/ai_detector.json</code> and its ONNX artifact; no fallback detections are
      generated.
    </div>

    <section class="stats-grid" aria-label="Perception status">
      <article class="stat-card">
        <span class="stat-label">Runtime</span>
        <strong>{{ status?.runtime || 'Unavailable' }}</strong>
        <small>{{ status?.execution_owner || 'Unknown owner' }}</small>
      </article>
      <article class="stat-card">
        <span class="stat-label">Model</span>
        <strong>{{ status?.active_model_name || 'None' }}</strong>
        <small>{{ shortDigest(status?.model_sha256) }}</small>
      </article>
      <article class="stat-card" :class="freshnessClass">
        <span class="stat-label">Latest result</span>
        <strong>{{ snapshot?.fresh ? 'Fresh' : 'Unavailable / stale' }}</strong>
        <small>{{ resultAgeLabel }}</small>
      </article>
      <article class="stat-card">
        <span class="stat-label">Route-cost objects</span>
        <strong>{{ snapshot?.route_cost_obstacle_count ?? 0 }}</strong>
        <small>Advisory only; ToF and gateway safety remain authoritative</small>
      </article>
    </section>

    <section class="card">
      <div class="card-header">
        <h2>Current frame result</h2>
        <span v-if="snapshot?.reason_code" class="reason-code">
          {{ snapshot.reason_code }}
        </span>
      </div>
      <div class="card-body">
        <div v-if="latestResult" class="provenance-grid">
          <div>
            <span>Frame</span><strong>{{ latestResult.input_frame_id }}</strong>
          </div>
          <div>
            <span>Timestamp</span><strong>{{ formatDate(latestResult.timestamp) }}</strong>
          </div>
          <div>
            <span>Latency</span><strong>{{ formatLatency(latestResult.total_time_ms) }}</strong>
          </div>
          <div>
            <span>Model version</span><strong>{{ latestResult.model_version }}</strong>
          </div>
          <div>
            <span>Runtime</span><strong>{{ latestResult.model_runtime }}</strong>
          </div>
          <div>
            <span>Artifact</span><strong>{{ shortDigest(latestResult.model_sha256) }}</strong>
          </div>
        </div>

        <div v-if="latestResult?.detected_objects.length" class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Class</th>
                <th>Confidence</th>
                <th>Distance</th>
                <th>Bearing</th>
                <th>Cost multiplier</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="object in latestResult.detected_objects" :key="object.object_id">
                <td>{{ object.class_name }}</td>
                <td>{{ formatPercent(object.confidence) }}</td>
                <td>{{ formatDistance(object.distance_estimate) }}</td>
                <td>{{ formatBearing(object.relative_bearing) }}</td>
                <td>{{ object.semantic_cost_multiplier.toFixed(1) }}×</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else-if="latestResult" class="empty-state">
          This fresh frame was processed and contained no detections above the configured threshold.
        </p>
        <p v-else class="empty-state">No validated perception result is available.</p>
      </div>
    </section>

    <section class="card">
      <div class="card-header"><h2>Recent validated results</h2></div>
      <div class="card-body recent-list">
        <button
          v-for="result in recentResults"
          :key="result.inference_id"
          class="recent-item"
          type="button"
          @click="selectResult(result)"
        >
          <span>{{ result.input_frame_id }}</span>
          <span>{{ result.detected_objects.length }} detections</span>
          <span>{{ formatLatency(result.total_time_ms) }}</span>
          <span>{{ formatDate(result.timestamp) }}</span>
        </button>
        <p v-if="!recentResults.length" class="empty-state">No inference history is available.</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, ref } from 'vue'
  import { useApiService } from '@/services/api'

  interface DetectedObject {
    object_id: string
    class_name: string
    confidence: number
    distance_estimate: number | null
    relative_bearing: number | null
    semantic_cost_multiplier: number
  }

  interface InferenceResult {
    inference_id: string
    input_frame_id: string
    timestamp: string
    detected_objects: DetectedObject[]
    total_time_ms: number
    model_name: string
    model_version: string
    model_runtime: string
    model_sha256: string | null
  }

  interface PerceptionSnapshot {
    available: boolean
    fresh: boolean
    reason_code: string | null
    result_age_seconds: number | null
    max_result_age_seconds: number
    route_cost_obstacle_count: number
    result: InferenceResult | null
  }

  interface AIStatus {
    initialized: boolean
    system_enabled: boolean
    model_ready: boolean
    active_model_name: string | null
    runtime: string | null
    execution_owner: string
    model_sha256: string | null
    last_error: string | null
  }

  const api = useApiService()
  const status = ref<AIStatus | null>(null)
  const snapshot = ref<PerceptionSnapshot | null>(null)
  const recentResults = ref<InferenceResult[]>([])
  const selectedResult = ref<InferenceResult | null>(null)
  const loading = ref(false)
  const runningInference = ref(false)
  const errorMessage = ref('')
  let refreshTimer: ReturnType<typeof setInterval> | null = null

  const latestResult = computed(() => selectedResult.value || snapshot.value?.result || null)
  const canRequestInference = computed(() =>
    Boolean(status.value?.model_ready && status.value.execution_owner === 'backend')
  )
  const freshnessClass = computed(() => ({
    'is-good': snapshot.value?.fresh === true,
    'is-warning': snapshot.value?.fresh !== true,
  }))
  const resultAgeLabel = computed(() => {
    const age = snapshot.value?.result_age_seconds
    if (age == null) return 'No timestamped result'
    return `${age.toFixed(1)} s old (limit ${snapshot.value?.max_result_age_seconds.toFixed(1)} s)`
  })

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      const [statusResponse, perceptionResponse, recentResponse] = await Promise.all([
        api.get('/api/v2/ai/status'),
        api.get('/api/v2/ai/perception/latest'),
        api.get('/api/v2/ai/results/recent?limit=10'),
      ])
      status.value = statusResponse.data as AIStatus
      snapshot.value = perceptionResponse.data as PerceptionSnapshot
      recentResults.value = recentResponse.data as InferenceResult[]
      errorMessage.value = ''
    } catch (error) {
      errorMessage.value =
        error instanceof Error ? error.message : 'Unable to load perception state'
    } finally {
      loading.value = false
    }
  }

  async function runLatestInference(): Promise<void> {
    if (!canRequestInference.value) return
    runningInference.value = true
    try {
      await api.post('/api/v2/ai/inference/latest')
      selectedResult.value = null
      await refresh()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Latest-frame inference failed'
    } finally {
      runningInference.value = false
    }
  }

  function selectResult(result: InferenceResult): void {
    selectedResult.value = result
  }

  function shortDigest(value: string | null | undefined): string {
    return value ? `${value.slice(0, 12)}…` : 'No validated digest'
  }

  function formatDate(value: string): string {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString()
  }

  function formatLatency(value: number): string {
    return Number.isFinite(value) ? `${value.toFixed(1)} ms` : 'Unknown'
  }

  function formatPercent(value: number): string {
    return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : 'Unknown'
  }

  function formatDistance(value: number | null): string {
    return value == null ? 'Unknown' : `${value.toFixed(2)} m`
  }

  function formatBearing(value: number | null): string {
    return value == null ? 'Unknown' : `${value.toFixed(1)}°`
  }

  onMounted(() => {
    void refresh()
    refreshTimer = setInterval(() => void refresh(), 2000)
  })

  onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
  })
</script>

<style scoped>
  .ai-view {
    display: grid;
    gap: 1.25rem;
  }
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }
  .page-header h1,
  .card-header h2 {
    margin: 0;
  }
  .text-muted,
  .stat-card small,
  .empty-state {
    color: var(--color-text-muted, #64748b);
  }
  .header-actions {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 1rem;
  }
  .stat-card,
  .card {
    border: 1px solid var(--color-border, #dbe2ea);
    border-radius: 0.75rem;
    background: var(--color-surface, #fff);
  }
  .stat-card {
    display: grid;
    gap: 0.35rem;
    padding: 1rem;
    border-left: 4px solid #64748b;
  }
  .stat-card.is-good {
    border-left-color: #16a34a;
  }
  .stat-card.is-warning {
    border-left-color: #d97706;
  }
  .stat-label {
    color: var(--color-text-muted, #64748b);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--color-border, #dbe2ea);
  }
  .card-body {
    padding: 1.25rem;
  }
  .reason-code {
    font-family: monospace;
    font-size: 0.8rem;
    color: #b45309;
  }
  .provenance-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .provenance-grid div {
    display: grid;
    gap: 0.2rem;
  }
  .provenance-grid span {
    color: var(--color-text-muted, #64748b);
    font-size: 0.8rem;
  }
  .table-wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    padding: 0.65rem;
    text-align: left;
    border-bottom: 1px solid var(--color-border, #e2e8f0);
  }
  th {
    font-size: 0.8rem;
    text-transform: uppercase;
    color: var(--color-text-muted, #64748b);
  }
  .recent-list {
    display: grid;
    gap: 0.5rem;
  }
  .recent-item {
    display: grid;
    grid-template-columns: minmax(120px, 1fr) repeat(3, auto);
    gap: 1rem;
    padding: 0.75rem;
    border: 1px solid var(--color-border, #e2e8f0);
    border-radius: 0.5rem;
    background: transparent;
    text-align: left;
    color: inherit;
  }
  .recent-item:hover {
    background: var(--color-surface-muted, #f8fafc);
  }
  .alert {
    padding: 0.9rem 1rem;
    border-radius: 0.5rem;
  }
  .alert-danger {
    background: #fee2e2;
    color: #991b1b;
  }
  .alert-warning {
    background: #fef3c7;
    color: #92400e;
  }
  code {
    font-family: ui-monospace, monospace;
  }
  @media (max-width: 760px) {
    .page-header {
      flex-direction: column;
    }
    .recent-item {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>

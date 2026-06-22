<template>
  <div class="power-history-view">
    <div class="retro-header">
      <div class="header-glow" />
      <h1 class="retro-title">POWER HISTORY</h1>
      <p class="retro-subtitle">BATTERY · SOLAR · LOAD — ACTIVITY TAGGED</p>
    </div>

    <!-- Controls -->
    <div class="controls-bar">
      <div class="control-group">
        <label>Window</label>
        <select v-model="windowHours" @change="fetchHistory">
          <option :value="1">1 hour</option>
          <option :value="6">6 hours</option>
          <option :value="24">24 hours</option>
          <option :value="48">48 hours</option>
          <option :value="168">7 days</option>
        </select>
      </div>
      <div class="control-group">
        <label>Resolution</label>
        <select v-model="resolutionMin" @change="fetchHistory">
          <option :value="0.5">30 s</option>
          <option :value="1">1 min</option>
          <option :value="5">5 min</option>
          <option :value="15">15 min</option>
          <option :value="60">1 hour</option>
        </select>
      </div>
      <button class="retro-btn refresh-btn" @click="fetchHistory" :disabled="loading">
        {{ loading ? 'LOADING…' : '↻ REFRESH' }}
      </button>
      <span v-if="lastRefresh" class="last-refresh">Updated {{ lastRefresh }}</span>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- Stats row -->
    <div class="stats-row" v-if="stats">
      <div class="stat-card">
        <div class="stat-label">AVG BATTERY</div>
        <div class="stat-value">{{ stats.avgBattV ?? '—' }} V</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">AVG SOLAR</div>
        <div class="stat-value">{{ stats.avgSolarW ?? '—' }} W</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">AVG LOAD</div>
        <div class="stat-value">{{ stats.avgLoadW ?? '—' }} W</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">MIN SOC</div>
        <div class="stat-value">{{ stats.minSoc ?? '—' }} %</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">MAX SOC</div>
        <div class="stat-value">{{ stats.maxSoc ?? '—' }} %</div>
      </div>
    </div>

    <!-- Charts -->
    <div class="charts-container">
      <!-- State of Charge -->
      <div class="retro-card chart-card">
        <div class="card-header"><h4>STATE OF CHARGE (%)</h4></div>
        <div class="chart-wrapper">
          <Line v-if="socChartData" :data="socChartData" :options="socChartOptions" />
          <div v-else class="no-data">No data available</div>
        </div>
      </div>

      <!-- Power (Solar vs Load) -->
      <div class="retro-card chart-card">
        <div class="card-header"><h4>POWER BALANCE (W)</h4></div>
        <div class="chart-wrapper">
          <Line v-if="powerChartData" :data="powerChartData" :options="powerChartOptions" />
          <div v-else class="no-data">No data available</div>
        </div>
      </div>

      <!-- Battery voltage -->
      <div class="retro-card chart-card">
        <div class="card-header"><h4>BATTERY VOLTAGE (V)</h4></div>
        <div class="chart-wrapper">
          <Line v-if="voltageChartData" :data="voltageChartData" :options="voltageChartOptions" />
          <div v-else class="no-data">No data available</div>
        </div>
      </div>
    </div>

    <!-- Activity legend -->
    <div class="retro-card legend-card">
      <div class="card-header"><h4>ACTIVITY LEGEND</h4></div>
      <div class="legend-items">
        <div v-for="tag in activityTags" :key="tag.value" class="legend-item">
          <span class="legend-dot" :style="{ background: tag.color }" />
          <span class="legend-label">{{ tag.label }}</span>
        </div>
      </div>
    </div>

    <!-- Data table (collapsible) -->
    <div class="retro-card table-card">
      <div class="card-header" @click="showTable = !showTable" style="cursor:pointer;">
        <h4>RAW DATA TABLE</h4>
        <span>{{ showTable ? '▲' : '▼' }}</span>
      </div>
      <div v-if="showTable" class="table-wrapper">
        <table class="power-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Batt V</th>
              <th>Batt A</th>
              <th>Solar W</th>
              <th>Load W</th>
              <th>SoC %</th>
              <th>Activity</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableData" :key="row.ts" :style="{ borderLeft: `3px solid ${activityColor(row.activity)}` }">
              <td>{{ formatTime(row.ts) }}</td>
              <td>{{ row.batt_v?.toFixed(2) ?? '—' }}</td>
              <td>{{ row.batt_a?.toFixed(2) ?? '—' }}</td>
              <td>{{ row.solar_w?.toFixed(1) ?? '—' }}</td>
              <td>{{ row.load_w?.toFixed(1) ?? '—' }}</td>
              <td>{{ row.soc_pct?.toFixed(1) ?? '—' }}</td>
              <td :style="{ color: activityColor(row.activity) }">{{ row.activity }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface PowerRow {
  ts: number
  iso_ts: string
  batt_v: number | null
  batt_a: number | null
  batt_w: number | null
  solar_w: number | null
  load_w: number | null
  soc_pct: number | null
  activity: string
}

interface ActivityTag {
  value: string
  label: string
  color: string
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const windowHours = ref(24)
const resolutionMin = ref(5)
const loading = ref(false)
const error = ref<string | null>(null)
const lastRefresh = ref<string | null>(null)
const showTable = ref(false)

const rows = ref<PowerRow[]>([])
const activityTags = ref<ActivityTag[]>([])

let autoRefreshTimer: ReturnType<typeof setInterval> | null = null

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------
async function fetchHistory() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(
      `/api/v2/power/history?hours=${windowHours.value}&resolution=${resolutionMin.value}`
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const json = await res.json()
    rows.value = json.data ?? []
    lastRefresh.value = new Date().toLocaleTimeString()
  } catch (e: any) {
    error.value = `Failed to load power history: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function fetchActivityTags() {
  try {
    const res = await fetch('/api/v2/power/activity-tags')
    if (!res.ok) return
    const json = await res.json()
    activityTags.value = json.tags ?? []
  } catch {
    // Non-fatal: defaults below
    activityTags.value = [
      { value: 'idle', label: 'Idle', color: '#6b7280' },
      { value: 'mowing', label: 'Mowing', color: '#16a34a' },
      { value: 'manual', label: 'Manual Drive', color: '#2563eb' },
      { value: 'returning', label: 'Returning Home', color: '#d97706' },
      { value: 'paused', label: 'Paused', color: '#9333ea' },
      { value: 'charging', label: 'Charging', color: '#0891b2' },
      { value: 'emergency_stop', label: 'Emergency Stop', color: '#dc2626' },
    ]
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function activityColor(activity: string): string {
  const tag = activityTags.value.find((t) => t.value === activity)
  return tag?.color ?? '#6b7280'
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

function avg(vals: (number | null)[]): string | null {
  const valid = vals.filter((v): v is number => v !== null)
  if (!valid.length) return null
  return (valid.reduce((a, b) => a + b, 0) / valid.length).toFixed(2)
}

function minVal(vals: (number | null)[]): string | null {
  const valid = vals.filter((v): v is number => v !== null)
  if (!valid.length) return null
  return Math.min(...valid).toFixed(1)
}

function maxVal(vals: (number | null)[]): string | null {
  const valid = vals.filter((v): v is number => v !== null)
  if (!valid.length) return null
  return Math.max(...valid).toFixed(1)
}

// ---------------------------------------------------------------------------
// Computed stats
// ---------------------------------------------------------------------------
const stats = computed(() => {
  if (!rows.value.length) return null
  return {
    avgBattV: avg(rows.value.map((r) => r.batt_v)),
    avgSolarW: avg(rows.value.map((r) => r.solar_w)),
    avgLoadW: avg(rows.value.map((r) => r.load_w)),
    minSoc: minVal(rows.value.map((r) => r.soc_pct)),
    maxSoc: maxVal(rows.value.map((r) => r.soc_pct)),
  }
})

const tableData = computed(() => [...rows.value].reverse().slice(0, 500))

// ---------------------------------------------------------------------------
// Chart helpers
// ---------------------------------------------------------------------------
function makeLabels(data: PowerRow[]): string[] {
  return data.map((r) => {
    const d = new Date(r.ts * 1000)
    return windowHours.value <= 6
      ? d.toLocaleTimeString()
      : `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  })
}

// Activity-coloured point background array
function pointColors(data: PowerRow[]): string[] {
  return data.map((r) => activityColor(r.activity))
}

const commonLineOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 0 },
  plugins: {
    legend: { labels: { color: '#cbd5e1', font: { family: 'monospace' } } },
    tooltip: {
      callbacks: {
        afterLabel: (ctx: any) => {
          const row = rows.value[ctx.dataIndex]
          return row ? `Activity: ${row.activity}` : ''
        },
      },
    },
  },
  scales: {
    x: { ticks: { color: '#64748b', maxRotation: 45, font: { size: 10 } }, grid: { color: '#1e293b' } },
    y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
  },
}

// ---------------------------------------------------------------------------
// Chart data
// ---------------------------------------------------------------------------
const socChartData = computed(() => {
  if (!rows.value.length) return null
  const labels = makeLabels(rows.value)
  return {
    labels,
    datasets: [
      {
        label: 'SoC %',
        data: rows.value.map((r) => r.soc_pct),
        borderColor: '#0891b2',
        backgroundColor: 'rgba(8, 145, 178, 0.1)',
        pointBackgroundColor: pointColors(rows.value),
        pointRadius: 3,
        fill: true,
        tension: 0.3,
      },
    ],
  }
})

const socChartOptions = computed(() => ({
  ...commonLineOptions,
  scales: {
    ...commonLineOptions.scales,
    y: { ...commonLineOptions.scales.y, min: 0, max: 100 },
  },
}))

const powerChartData = computed(() => {
  if (!rows.value.length) return null
  const labels = makeLabels(rows.value)
  return {
    labels,
    datasets: [
      {
        label: 'Solar (W)',
        data: rows.value.map((r) => r.solar_w),
        borderColor: '#f59e0b',
        backgroundColor: 'transparent',
        pointBackgroundColor: pointColors(rows.value),
        pointRadius: 2,
        tension: 0.3,
      },
      {
        label: 'Load (W)',
        data: rows.value.map((r) => r.load_w),
        borderColor: '#ef4444',
        backgroundColor: 'transparent',
        pointBackgroundColor: pointColors(rows.value),
        pointRadius: 2,
        tension: 0.3,
      },
    ],
  }
})

const powerChartOptions = computed(() => ({ ...commonLineOptions }))

const voltageChartData = computed(() => {
  if (!rows.value.length) return null
  const labels = makeLabels(rows.value)
  return {
    labels,
    datasets: [
      {
        label: 'Batt V',
        data: rows.value.map((r) => r.batt_v),
        borderColor: '#16a34a',
        backgroundColor: 'rgba(22, 163, 74, 0.08)',
        pointBackgroundColor: pointColors(rows.value),
        pointRadius: 2,
        fill: true,
        tension: 0.3,
      },
    ],
  }
})

const voltageChartOptions = computed(() => ({ ...commonLineOptions }))

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(async () => {
  await Promise.all([fetchActivityTags(), fetchHistory()])
  // Auto-refresh every 10 s
  autoRefreshTimer = setInterval(fetchHistory, 10_000)
})

onUnmounted(() => {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer)
})
</script>

<style scoped>
.power-history-view {
  padding: 16px;
  background: #0a0f1a;
  min-height: 100vh;
  color: #e2e8f0;
}

.retro-header {
  text-align: center;
  padding: 20px 0 12px;
  position: relative;
}

.header-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 50% 0%, rgba(8, 145, 178, 0.12) 0%, transparent 70%);
  pointer-events: none;
}

.retro-title {
  font-family: monospace;
  font-size: 1.6rem;
  letter-spacing: 0.15em;
  color: #0891b2;
  text-shadow: 0 0 18px rgba(8, 145, 178, 0.6);
  margin: 0;
}

.retro-subtitle {
  font-family: monospace;
  font-size: 0.75rem;
  color: #64748b;
  letter-spacing: 0.12em;
  margin: 4px 0 0;
}

.controls-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin: 16px 0;
  padding: 12px 16px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: monospace;
  font-size: 0.75rem;
  color: #94a3b8;
}

.control-group select {
  background: #1e293b;
  border: 1px solid #334155;
  color: #e2e8f0;
  border-radius: 4px;
  padding: 4px 8px;
  font-family: monospace;
  font-size: 0.75rem;
}

.retro-btn {
  padding: 6px 16px;
  background: transparent;
  border: 1px solid #0891b2;
  color: #0891b2;
  font-family: monospace;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.retro-btn:hover:not(:disabled) {
  background: rgba(8, 145, 178, 0.15);
}

.retro-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.last-refresh {
  font-family: monospace;
  font-size: 0.7rem;
  color: #475569;
}

.error-banner {
  background: rgba(220, 38, 38, 0.15);
  border: 1px solid #dc2626;
  color: #fca5a5;
  padding: 8px 16px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8rem;
  margin-bottom: 12px;
}

.stats-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.stat-card {
  flex: 1;
  min-width: 100px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 10px 14px;
  text-align: center;
}

.stat-label {
  font-family: monospace;
  font-size: 0.65rem;
  color: #64748b;
  letter-spacing: 0.08em;
}

.stat-value {
  font-family: monospace;
  font-size: 1.1rem;
  color: #0891b2;
  font-weight: 600;
  margin-top: 4px;
}

.charts-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 16px;
}

.retro-card {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #1e293b;
}

.card-header h4 {
  font-family: monospace;
  font-size: 0.75rem;
  letter-spacing: 0.1em;
  color: #94a3b8;
  margin: 0;
}

.chart-wrapper {
  height: 220px;
  padding: 12px 8px 8px;
  position: relative;
}

.no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-family: monospace;
  font-size: 0.8rem;
  color: #475569;
}

.legend-card {
  margin-bottom: 16px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: monospace;
  font-size: 0.75rem;
  color: #94a3b8;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.table-card {
  margin-bottom: 32px;
}

.table-wrapper {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.power-table {
  width: 100%;
  border-collapse: collapse;
  font-family: monospace;
  font-size: 0.75rem;
}

.power-table th,
.power-table td {
  padding: 6px 12px;
  border-bottom: 1px solid #1e293b;
  text-align: left;
  white-space: nowrap;
}

.power-table th {
  background: #0a0f1a;
  color: #64748b;
  letter-spacing: 0.06em;
  font-size: 0.7rem;
  position: sticky;
  top: 0;
}

.power-table td {
  color: #cbd5e1;
}

.power-table tr:hover td {
  background: rgba(30, 41, 59, 0.4);
}
</style>

<template>
  <div class="rtk-panel">
    <div class="panel-header">
      <h2>RTK Diagnostics</h2>
      <div class="actions">
        <button class="btn" @click="refreshNow">Refresh</button>
        <label class="poll-label">
          <input type="checkbox" v-model="autoRefresh" /> Auto-refresh
        </label>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-title">NTRIP</div>
        <div class="kv"><span>Connected</span><strong :class="ntrip?.connected ? 'ok' : 'warn'">{{ fmtBool(ntrip?.connected) }}</strong></div>
        <div class="kv"><span>Host</span><code>{{ ntrip?.host }}:{{ ntrip?.port }}</code></div>
        <div class="kv"><span>Mountpoint</span><code>{{ ntrip?.mountpoint }}</code></div>
        <div class="kv"><span>Serial</span><code>{{ ntrip?.serial_device }} @ {{ ntrip?.baudrate }}</code></div>
        <div class="kv"><span>GGA</span><span>{{ ntrip?.gga_configured ? `enabled (${ntrip?.gga_interval_s}s)` : 'disabled' }}</span></div>
        <div class="kv"><span>Total bytes</span><strong>{{ formatBytes(ntrip?.total_bytes_forwarded) }}</strong></div>
        <div class="kv"><span>Rate</span><strong>{{ formatRate(ntrip?.approx_rate_bps) }}</strong></div>
        <div class="kv"><span>Last forward age</span><span>{{ formatSeconds(ntrip?.last_forward_age_s) }}</span></div>
      </div>

      <div class="card">
        <div class="card-title">GPS</div>
        <div class="kv"><span>Mode</span><code>{{ gps?.mode }}</code></div>
        <div class="kv"><span>RTK status</span><strong :class="statusClass(gps?.rtk_status)">{{ gps?.rtk_status || 'unknown' }}</strong></div>
        <div class="kv"><span>HDOP</span><span>{{ fmtNum(gps?.last_hdop) }}</span></div>
        <div class="kv"><span>Satellites</span><span>{{ gps?.satellites ?? '—' }}</span></div>
        <div class="kv" v-if="gps?.reading">
          <span>Lat, Lon</span>
          <code>{{ fmtNum(gps.reading.latitude) }}, {{ fmtNum(gps.reading.longitude) }}</code>
        </div>
        <div class="kv" v-if="gps?.reading">
          <span>Altitude</span>
          <span>{{ fmtNum(gps.reading.altitude) }} m</span>
        </div>
        <div class="kv" v-if="gps?.reading">
          <span>Accuracy</span>
          <span>{{ fmtNum(gps.reading.accuracy) }} m</span>
        </div>
      </div>

      <div class="card">
        <div class="card-title">NMEA (last seen)</div>
        <details class="nmea">
          <summary>Show NMEA</summary>
          <pre>{{ formatNmea(nmea) }}</pre>
        </details>
      </div>
    </div>

    <div v-if="hardware" class="hw">
      <span>Hardware:</span>
      <code>gps_type={{ hardware.gps_type }} ntrip={{ hardware.gps_ntrip_enabled }}</code>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useApiService } from '@/services/api'

const api = useApiService()
const ntrip = ref<any | null>(null)
const gps = ref<any | null>(null)
const nmea = ref<Record<string, string> | null>(null)
const hardware = ref<any | null>(null)
const autoRefresh = ref(true)
let timer: any = null

async function load() {
  try {
    const resp = await api.get('/api/v2/sensors/gps/rtk/diagnostics')
    const data = resp?.data || {}
    ntrip.value = data.ntrip || null
    gps.value = data.gps || null
    nmea.value = (data.gps && data.gps.nmea) ? data.gps.nmea : null
    hardware.value = data.hardware || null
  } catch (e) {
    // non-fatal for UI; keep last seen
  }
}

function refreshNow() { load() }

onMounted(() => {
  load()
  timer = setInterval(() => { if (autoRefresh.value) load() }, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function fmtBool(v: any) { return v ? 'yes' : 'no' }
function fmtNum(v: any) { return (v === null || v === undefined) ? '—' : Number(v).toFixed(3) }
function formatRate(bps: any) {
  if (bps === null || bps === undefined) return '—'
  const val = Number(bps)
  if (!isFinite(val)) return '—'
  if (val > 1000) return (val/1000).toFixed(1) + ' kB/s'
  return val.toFixed(0) + ' B/s'
}
function formatBytes(b: any) {
  const val = Number(b || 0)
  if (val > 1024*1024) return (val/1024/1024).toFixed(1) + ' MB'
  if (val > 1024) return (val/1024).toFixed(1) + ' KB'
  return val.toFixed(0) + ' B'
}
function formatSeconds(s: any) {
  if (s === null || s === undefined) return '—'
  return Number(s).toFixed(1) + ' s'
}
function statusClass(s: string | undefined) {
  if (!s) return ''
  if (s.includes('FIXED')) return 'ok'
  if (s.includes('FLOAT')) return 'warn'
  return ''
}
function formatNmea(obj: Record<string, string> | null) {
  if (!obj) return '—'
  const keys = Object.keys(obj)
  return keys.map(k => `${k}: ${obj[k]}`).join('\n')
}
</script>

<style scoped>
.rtk-panel {
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--primary-light);
  background: var(--primary-dark);
}
.panel-header h2 { margin: 0; color: var(--accent-green); }
.actions { display: flex; align-items: center; gap: .75rem; }
.btn { background: var(--accent-green); color: #0a0a0a; border: none; padding: .5rem .9rem; cursor: pointer; border-radius: 4px; }
.btn:hover { filter: brightness(1.1); }
.poll-label { font-size: .9rem; color: var(--text-muted); }

.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; padding: 1rem; }
.card { border: 1px solid var(--primary-light); border-radius: 6px; padding: .75rem 1rem; background: rgba(0,0,0,0.25); }
.card-title { color: var(--primary-light); font-weight: 600; margin-bottom: .5rem; text-transform: uppercase; letter-spacing: .5px; }
.kv { display: flex; align-items: center; justify-content: space-between; padding: .25rem 0; gap: 1rem; }
.kv code { color: var(--accent-cyan, #00ffff); }
.ok { color: #00ff88; }
.warn { color: #ffdd55; }
.nmea pre { white-space: pre-wrap; background: rgba(0,0,0,0.3); padding: .5rem; border-radius: 4px; border: 1px solid var(--primary-light); }
.hw { padding: 0 1rem 1rem; color: var(--text-muted); }
</style>

<template>
  <div class="planning-view">
    <div class="page-header">
      <h1>Planning</h1>
      <p class="text-muted">Schedule and plan operations</p>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-header"><strong>Weather</strong></div>
        <div class="card-body">
          <div v-if="loadingWeather" class="text-muted">Loading weather…</div>
          <div v-else-if="weatherError" class="text-danger">{{ weatherError }}</div>
          <div v-else class="weather-grid">
            <div>
              <div class="label">Temperature</div>
              <div class="value">{{ current?.temperature_c.toFixed(1) }} °C</div>
            </div>
            <div>
              <div class="label">Humidity</div>
              <div class="value">{{ current?.humidity_percent.toFixed(0) }}%</div>
            </div>
            <div>
              <div class="label">Wind</div>
              <div class="value">{{ current?.wind_speed_mps.toFixed(1) }} m/s</div>
            </div>
            <div>
              <div class="label">Condition</div>
              <div class="value">{{ current?.condition }}</div>
            </div>
            <div>
              <div class="label">Source</div>
              <div class="value small">{{ current?.source }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card advice">
        <div class="card-header"><strong>Planning advice</strong></div>
        <div class="card-body">
          <div v-if="loadingAdvice" class="text-muted">Computing advice…</div>
          <div v-else-if="adviceError" class="text-danger">{{ adviceError }}</div>
          <div v-else>
            <div class="advice-pill" :class="adviceClass">{{ advice?.advice }}</div>
            <div class="reason">{{ advice?.reason }}</div>
            <div class="next-review">Next review at: {{ formatTs(advice?.next_review_at) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { weatherApi } from '@/composables/useApi'

type WeatherCurrent = {
  temperature_c: number
  humidity_percent: number
  wind_speed_mps: number
  condition: string
  source: string
  ts: string
}

type PlanningAdvice = {
  advice: 'proceed' | 'avoid' | 'caution'
  reason: string
  next_review_at: string
}

const loadingWeather = ref(true)
const loadingAdvice = ref(true)
const weatherError = ref<string | null>(null)
const adviceError = ref<string | null>(null)
const current = ref<WeatherCurrent | null>(null)
const advice = ref<PlanningAdvice | null>(null)

onMounted(async () => {
  try {
    current.value = await weatherApi.getCurrent()
  } catch (e: any) {
    weatherError.value = e?.message ?? 'Failed to load weather'
  } finally {
    loadingWeather.value = false
  }

  try {
    advice.value = await weatherApi.getPlanningAdvice()
  } catch (e: any) {
    adviceError.value = e?.message ?? 'Failed to load advice'
  } finally {
    loadingAdvice.value = false
  }
})

const adviceClass = computed(() => {
  switch (advice.value?.advice) {
    case 'proceed':
      return 'ok'
    case 'caution':
      return 'warn'
    case 'avoid':
      return 'bad'
    default:
      return 'unknown'
  }
})

function formatTs(ts?: string) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch {
    return ts
  }
}
</script>

<style scoped>
.planning-view {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
}

.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

@media (min-width: 768px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
}

.card {
  border: 1px solid #2c3e50;
  border-radius: 8px;
  background: #0b111b;
}

.card-header {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #2c3e50;
}

.card-body {
  padding: 1rem;
}

.weather-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem 1rem;
}

.label {
  font-size: 0.85rem;
  color: #9aa4b2;
}

.value {
  font-weight: 600;
}

.value.small {
  font-size: 0.8rem;
  color: #9aa4b2;
}

.advice .advice-pill {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-weight: 700;
  text-transform: uppercase;
}

.advice .advice-pill.ok { background: #1f883d; }
.advice .advice-pill.warn { background: #9a6700; }
.advice .advice-pill.bad { background: #cf222e; }
.advice .advice-pill.unknown { background: #57606a; }

.reason {
  margin-top: 0.5rem;
}

.next-review {
  margin-top: 0.25rem;
  color: #9aa4b2;
  font-size: 0.85rem;
}
</style>
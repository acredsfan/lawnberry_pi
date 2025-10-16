import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '@/composables/useApi'

type UnitSystem = 'metric' | 'imperial'

const STORAGE_KEY = 'lb_unit_system'

function normalizeUnit(value: unknown): UnitSystem | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.trim().toLowerCase()
  if (normalized === 'metric' || normalized === 'imperial') {
    return normalized
  }
  return null
}

function extractUnitFromSettings(payload: unknown): UnitSystem | null {
  if (!payload || typeof payload !== 'object') {
    return null
  }
  const candidates = [
    (payload as any)?.system?.ui?.unit_system,
    (payload as any)?.system?.unit_system,
    (payload as any)?.categories?.system?.ui?.unit_system,
    (payload as any)?.categories?.system?.unit_system,
    (payload as any)?.ui?.unit_system,
    (payload as any)?.unit_system,
  ]
  for (const candidate of candidates) {
    const unit = normalizeUnit(candidate)
    if (unit) {
      return unit
    }
  }
  return null
}

function resolveInitialUnit(): UnitSystem {
  if (typeof window === 'undefined') {
    return 'metric'
  }
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'metric' || stored === 'imperial') {
      return stored
    }
  } catch {
    // Ignore storage access issues (private browsing, etc.)
  }
  return 'metric'
}

export const usePreferencesStore = defineStore('preferences', () => {
  const unitSystem = ref<UnitSystem>(resolveInitialUnit())
  const initialized = ref(false)
  const syncing = ref(false)

  const setUnitSystem = (value: UnitSystem) => {
    if (unitSystem.value === value) {
      initialized.value = true
      return
    }
    unitSystem.value = value
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, value)
      }
    } catch {
      // Storage errors are non-fatal; preference still updates in-memory.
    }
    initialized.value = true
  }

  const ensureInitialized = () => {
    if (initialized.value) {
      return
    }
    const current = unitSystem.value
    if (current !== 'metric' && current !== 'imperial') {
      unitSystem.value = 'metric'
    }
    initialized.value = true
  }

  const syncWithServer = async () => {
    ensureInitialized()
    if (syncing.value) {
      return
    }
    try {
      syncing.value = true
      const settings = await settingsApi.getSettings()
      const unit = extractUnitFromSettings(settings)
      if (unit) {
        setUnitSystem(unit)
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn('Failed to sync measurement preference', error)
      }
    } finally {
      syncing.value = false
    }
  }

  return {
    unitSystem,
    setUnitSystem,
    ensureInitialized,
    syncWithServer,
  }
})

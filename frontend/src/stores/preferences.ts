import { defineStore } from 'pinia'
import { ref } from 'vue'

type UnitSystem = 'metric' | 'imperial'

const STORAGE_KEY = 'lb_unit_system'

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

  return {
    unitSystem,
    setUnitSystem,
    ensureInitialized,
  }
})

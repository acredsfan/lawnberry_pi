import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { SystemSettings } from '../../types'

const initialState: SystemSettings = {
  units: {
    temperature: 'celsius',
    distance: 'metric',
    speed: 'ms'
  },
  safety: {
    emergencyStopDistance: 0.5,
    maxSlope: 15,
    obstacleDetectionSensitivity: 0.8,
    responseTime: 100
  },
  operation: {
    defaultSpeed: 1.0,
    batteryThresholds: {
      low: 20,
      critical: 10,
      return: 30
    }
  },
  display: {
    theme: 'light',
    refreshRate: 1000,
    showAdvanced: false
  }
}

const settingsSlice = createSlice({
  name: 'settings',
  initialState,
  reducers: {
    updateUnits: (state, action: PayloadAction<Partial<SystemSettings['units']>>) => {
      state.units = { ...state.units, ...action.payload }
    },
    updateSafety: (state, action: PayloadAction<Partial<SystemSettings['safety']>>) => {
      state.safety = { ...state.safety, ...action.payload }
    },
    updateOperation: (state, action: PayloadAction<Partial<SystemSettings['operation']>>) => {
      state.operation = { ...state.operation, ...action.payload }
    },
    updateDisplay: (state, action: PayloadAction<Partial<SystemSettings['display']>>) => {
      state.display = { ...state.display, ...action.payload }
    },
    updateBatteryThresholds: (state, action: PayloadAction<Partial<SystemSettings['operation']['batteryThresholds']>>) => {
      state.operation.batteryThresholds = { ...state.operation.batteryThresholds, ...action.payload }
    },
    resetToDefaults: () => initialState
  }
})

export const {
  updateUnits,
  updateSafety,
  updateOperation,
  updateDisplay,
  updateBatteryThresholds,
  resetToDefaults
} = settingsSlice.actions

export default settingsSlice.reducer

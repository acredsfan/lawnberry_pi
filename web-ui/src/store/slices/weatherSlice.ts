import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { WeatherData } from '../../types'

interface WeatherState {
  data: WeatherData | null
  isLoading: boolean
  error: string | null
  lastUpdate: number | null
  preferences: {
    units: 'metric' | 'imperial'
    autoRefresh: boolean
    refreshInterval: number
  }
}

const initialState: WeatherState = {
  data: null,
  isLoading: false,
  error: null,
  lastUpdate: null,
  preferences: {
    units: 'metric',
    autoRefresh: true,
    refreshInterval: 600000 // 10 minutes
  }
}

const weatherSlice = createSlice({
  name: 'weather',
  initialState,
  reducers: {
    setWeatherData: (state, action: PayloadAction<WeatherData>) => {
      state.data = action.payload
      state.lastUpdate = Date.now()
      state.error = null
      state.isLoading = false
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload
      state.isLoading = false
    },
    clearError: (state) => {
      state.error = null
    },
    updatePreferences: (state, action: PayloadAction<Partial<WeatherState['preferences']>>) => {
      state.preferences = { ...state.preferences, ...action.payload }
    }
  }
})

export const {
  setWeatherData,
  setLoading,
  setError,
  clearError,
  updatePreferences
} = weatherSlice.actions

export default weatherSlice.reducer

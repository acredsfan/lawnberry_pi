import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { NavigationState } from '../../types'

interface NavigationSliceState extends NavigationState {
  isNavigating: boolean
  error: string | null
  mapCenter: { lat: number; lng: number } | null
  mapZoom: number
  showCoverage: boolean
  showObstacles: boolean
  showPath: boolean
}

const initialState: NavigationSliceState = {
  currentPath: [],
  plannedPath: [],
  obstacles: [],
  coverage: [],
  isNavigating: false,
  error: null,
  mapCenter: null,
  mapZoom: 18,
  showCoverage: true,
  showObstacles: true,
  showPath: true
}

const navigationSlice = createSlice({
  name: 'navigation',
  initialState,
  reducers: {
    setCurrentPath: (state, action: PayloadAction<Array<{ lat: number; lng: number }>>) => {
      state.currentPath = action.payload
    },
    setPlannedPath: (state, action: PayloadAction<Array<{ lat: number; lng: number }>>) => {
      state.plannedPath = action.payload
    },
    addPathPoint: (state, action: PayloadAction<{ lat: number; lng: number }>) => {
      state.currentPath.push(action.payload)
      // Keep only last 1000 points for performance
      if (state.currentPath.length > 1000) {
        state.currentPath = state.currentPath.slice(-1000)
      }
    },
    setObstacles: (state, action: PayloadAction<NavigationSliceState['obstacles']>) => {
      state.obstacles = action.payload
    },
    addObstacle: (state, action: PayloadAction<NavigationSliceState['obstacles'][0]>) => {
      const existingIndex = state.obstacles.findIndex(o => o.id === action.payload.id)
      if (existingIndex >= 0) {
        state.obstacles[existingIndex] = action.payload
      } else {
        state.obstacles.push(action.payload)
      }
    },
    removeObstacle: (state, action: PayloadAction<string>) => {
      state.obstacles = state.obstacles.filter(o => o.id !== action.payload)
    },
    setCoverage: (state, action: PayloadAction<Array<{ lat: number; lng: number; covered: boolean }>>) => {
      state.coverage = action.payload
    },
    updateCoveragePoint: (state, action: PayloadAction<{ lat: number; lng: number; covered: boolean }>) => {
      const existingIndex = state.coverage.findIndex(
        c => Math.abs(c.lat - action.payload.lat) < 0.00001 && Math.abs(c.lng - action.payload.lng) < 0.00001
      )
      if (existingIndex >= 0) {
        state.coverage[existingIndex] = action.payload
      } else {
        state.coverage.push(action.payload)
      }
    },
    setNavigating: (state, action: PayloadAction<boolean>) => {
      state.isNavigating = action.payload
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload
    },
    setMapCenter: (state, action: PayloadAction<{ lat: number; lng: number } | null>) => {
      state.mapCenter = action.payload
    },
    setMapZoom: (state, action: PayloadAction<number>) => {
      state.mapZoom = action.payload
    },
    toggleCoverage: (state) => {
      state.showCoverage = !state.showCoverage
    },
    toggleObstacles: (state) => {
      state.showObstacles = !state.showObstacles
    },
    togglePath: (state) => {
      state.showPath = !state.showPath
    },
    clearNavigation: (state) => {
      state.currentPath = []
      state.plannedPath = []
      state.obstacles = []
      state.coverage = []
      state.error = null
      state.isNavigating = false
    }
  }
})

export const {
  setCurrentPath,
  setPlannedPath,
  addPathPoint,
  setObstacles,
  addObstacle,
  removeObstacle,
  setCoverage,
  updateCoveragePoint,
  setNavigating,
  setError,
  setMapCenter,
  setMapZoom,
  toggleCoverage,
  toggleObstacles,
  togglePath,
  clearNavigation
} = navigationSlice.actions

export default navigationSlice.reducer

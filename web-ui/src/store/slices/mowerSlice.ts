import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { MowerStatus, Schedule, MowingPattern, YardBoundary } from '../../types'
import { Boundary } from '../../services/boundaryService'

interface MowerState {
  status: MowerStatus | null
  isConnected: boolean
  schedules: Schedule[]
  patterns: MowingPattern[]
  boundaries: YardBoundary[]
  yardBoundaries: Boundary[]
  currentSchedule: string | null
  currentPattern: string | null
  emergencyStop: boolean
  lastCommand: string | null
  commandHistory: Array<{
    command: string
    timestamp: number
    result: 'success' | 'error' | 'pending'
  }>
  boundaryLoading: boolean
  boundaryError: string | null
}

const initialState: MowerState = {
  status: null,
  isConnected: false,
  schedules: [],
  patterns: [
    {
      id: 'parallel',
      name: 'Parallel Lines',
      description: 'Simple back-and-forth pattern',
      type: 'parallel',
      parameters: { spacing: 0.3, angle: 0, overlap: 0.1 }
    },
    {
      id: 'checkerboard',
      name: 'Checkerboard',
      description: 'Alternating squares pattern',
      type: 'checkerboard',
      parameters: { spacing: 0.5, overlap: 0.05 }
    },
    {
      id: 'spiral',
      name: 'Spiral',
      description: 'Inside-out spiral pattern',
      type: 'spiral',
      parameters: { spacing: 0.3 }
    },
    {
      id: 'waves',
      name: 'Waves', 
      description: 'Sinusoidal wave pattern for natural appearance and excellent coverage',
      type: 'waves',
      parameters: { 
        amplitude: 0.75,
        wavelength: 8.0,
        base_angle: 0,
        spacing: 0.4,
        overlap: 0.1 
      }
    },
    {
      id: 'crosshatch',
      name: 'Crosshatch',
      description: 'Overlapping perpendicular lines for maximum coverage and cut quality',
      type: 'crosshatch',
      parameters: { 
        first_angle: 45,
        second_angle: 135,
        spacing: 0.3,
        overlap: 0.1 
      }
    }
  ],
  boundaries: [],
  yardBoundaries: [],
  currentSchedule: null,
  currentPattern: null,
  emergencyStop: false,
  lastCommand: null,
  commandHistory: [],
  boundaryLoading: false,
  boundaryError: null
}

const mowerSlice = createSlice({
  name: 'mower',
  initialState,
  reducers: {
    setStatus: (state, action: PayloadAction<MowerStatus>) => {
      state.status = action.payload
      state.isConnected = true
    },
    setConnectionState: (state, action: PayloadAction<boolean>) => {
      state.isConnected = action.payload
      if (!action.payload) {
        state.status = null
      }
    },
    addSchedule: (state, action: PayloadAction<Schedule>) => {
      state.schedules.push(action.payload)
    },
    updateSchedule: (state, action: PayloadAction<Schedule>) => {
      const index = state.schedules.findIndex(s => s.id === action.payload.id)
      if (index >= 0) {
        state.schedules[index] = action.payload
      }
    },
    deleteSchedule: (state, action: PayloadAction<string>) => {
      state.schedules = state.schedules.filter(s => s.id !== action.payload)
    },
    setCurrentSchedule: (state, action: PayloadAction<string | null>) => {
      state.currentSchedule = action.payload
    },
    setCurrentPattern: (state, action: PayloadAction<string>) => {
      state.currentPattern = action.payload
    },
    addBoundary: (state, action: PayloadAction<YardBoundary>) => {
      state.boundaries.push(action.payload)
    },
    updateBoundary: (state, action: PayloadAction<YardBoundary>) => {
      const index = state.boundaries.findIndex(b => b.id === action.payload.id)
      if (index >= 0) {
        state.boundaries[index] = action.payload
      }
    },
    deleteBoundary: (state, action: PayloadAction<string>) => {
      state.boundaries = state.boundaries.filter(b => b.id !== action.payload)
    },
    setEmergencyStop: (state, action: PayloadAction<boolean>) => {
      state.emergencyStop = action.payload
    },
    addCommand: (state, action: PayloadAction<{
      command: string
      result?: 'success' | 'error' | 'pending'
    }>) => {
      state.lastCommand = action.payload.command
      state.commandHistory.unshift({
        command: action.payload.command,
        timestamp: Date.now(),
        result: action.payload.result || 'pending'
      })
      // Keep only last 50 commands
      if (state.commandHistory.length > 50) {
        state.commandHistory = state.commandHistory.slice(0, 50)
      }
    },
    updateCommandResult: (state, action: PayloadAction<{
      command: string
      result: 'success' | 'error'
    }>) => {
      const command = state.commandHistory.find(c => 
        c.command === action.payload.command && c.result === 'pending'
      )
      if (command) {
        command.result = action.payload.result
      }
    }
  }
})

export const {
  setStatus,
  setConnectionState,
  addSchedule,
  updateSchedule,
  deleteSchedule,
  setCurrentSchedule,
  setCurrentPattern,
  addBoundary,
  updateBoundary,
  deleteBoundary,
  setEmergencyStop,
  addCommand,
  updateCommandResult
} = mowerSlice.actions

// Additional boundary management actions will be added via thunks

export default mowerSlice.reducer

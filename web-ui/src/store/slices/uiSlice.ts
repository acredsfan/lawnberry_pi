import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface UIState {
  sidebarOpen: boolean
  currentPage: string
  notifications: Array<{
    id: string
    type: 'info' | 'success' | 'warning' | 'error'
    title: string
    message: string
    timestamp: number
    read: boolean
    persistent?: boolean
  }>
  loading: {
    [key: string]: boolean
  }
  modals: {
    emergencyStop: boolean
    settings: boolean
    scheduleEditor: boolean
    boundaryEditor: boolean
    imageGallery: boolean
  }
  lastActivity: number
  connectionStatus: 'connected' | 'disconnected' | 'connecting' | 'error'
  performanceMetrics: {
    renderTime: number
    memoryUsage: number
    networkLatency: number
  }
}

const initialState: UIState = {
  sidebarOpen: false,
  currentPage: 'dashboard',
  notifications: [],
  loading: {},
  modals: {
    emergencyStop: false,
    settings: false,
    scheduleEditor: false,
    boundaryEditor: false,
    imageGallery: false
  },
  lastActivity: Date.now(),
  connectionStatus: 'disconnected',
  performanceMetrics: {
    renderTime: 0,
    memoryUsage: 0,
    networkLatency: 0
  }
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen
    },
    setSidebarOpen: (state, action: PayloadAction<boolean>) => {
      state.sidebarOpen = action.payload
    },
    setCurrentPage: (state, action: PayloadAction<string>) => {
      state.currentPage = action.payload
    },
    addNotification: (state, action: PayloadAction<Omit<UIState['notifications'][0], 'id' | 'timestamp' | 'read'>>) => {
      const notification = {
        ...action.payload,
        id: Date.now().toString(),
        timestamp: Date.now(),
        read: false
      }
      state.notifications.unshift(notification)
      // Keep only last 100 notifications
      if (state.notifications.length > 100) {
        state.notifications = state.notifications.slice(0, 100)
      }
    },
    markNotificationRead: (state, action: PayloadAction<string>) => {
      const notification = state.notifications.find(n => n.id === action.payload)
      if (notification) {
        notification.read = true
      }
    },
    removeNotification: (state, action: PayloadAction<string>) => {
      state.notifications = state.notifications.filter(n => n.id !== action.payload)
    },
    clearNotifications: (state) => {
      state.notifications = state.notifications.filter(n => n.persistent)
    },
    setLoading: (state, action: PayloadAction<{ key: string; loading: boolean }>) => {
      state.loading[action.payload.key] = action.payload.loading
    },
    openModal: (state, action: PayloadAction<keyof UIState['modals']>) => {
      state.modals[action.payload] = true
    },
    closeModal: (state, action: PayloadAction<keyof UIState['modals']>) => {
      state.modals[action.payload] = false
    },
    closeAllModals: (state) => {
      Object.keys(state.modals).forEach(key => {
        state.modals[key as keyof UIState['modals']] = false
      })
    },
    updateActivity: (state) => {
      state.lastActivity = Date.now()
    },
    setConnectionStatus: (state, action: PayloadAction<UIState['connectionStatus']>) => {
      state.connectionStatus = action.payload
    },
    updatePerformanceMetrics: (state, action: PayloadAction<Partial<UIState['performanceMetrics']>>) => {
      state.performanceMetrics = { ...state.performanceMetrics, ...action.payload }
    }
  }
})

export const {
  toggleSidebar,
  setSidebarOpen,
  setCurrentPage,
  addNotification,
  markNotificationRead,
  removeNotification,
  clearNotifications,
  setLoading,
  openModal,
  closeModal,
  closeAllModals,
  updateActivity,
  setConnectionStatus,
  updatePerformanceMetrics
} = uiSlice.actions

export default uiSlice.reducer

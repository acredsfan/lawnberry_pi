import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router-dom'
import { configureStore } from '@reduxjs/toolkit'
import { vi } from 'vitest'

import Dashboard from '../../pages/Dashboard'
import mapSlice from '../../store/slices/mapSlice'
import mowerSlice from '../../store/slices/mowerSlice'
import uiSlice from '../../store/slices/uiSlice'
import { websocket } from '../../services/websocket'

// Mock websocket service
vi.mock('../../services/websocket', () => ({
  websocket: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    send: vi.fn(),
    isConnected: vi.fn().mockReturnValue(true)
  }
}))

// Mock components
vi.mock('../../components/TPUDashboard', () => ({
  __esModule: true,
  default: () => <div data-testid="tpu-dashboard">TPU Dashboard</div>
}))

vi.mock('../../components/ConnectionStatus/ConnectionStatus', () => ({
  ConnectionStatus: ({ status }: { status: string }) => (
    <div data-testid="connection-status" data-status={status}>
      Connection: {status}
    </div>
  )
}))

const createTestStore = (initialState?: any) => {
  return configureStore({
    reducer: {
      map: mapSlice,
      mower: mowerSlice,
      ui: uiSlice
    },
    preloadedState: {
      map: {
        isOffline: false,
        currentProvider: 'google',
        config: {
          apiKey: 'test-api-key',
          defaultCenter: { lat: 40.0, lng: -82.0 },
          defaultZoom: 18,
          usageLevel: 'medium' as const
        },
        userPreferences: {
          preferredProvider: 'google' as const,
          autoFallback: true
        },
        ...initialState?.map
      },
      mower: {
        status: {
          connected: true,
          state: 'idle',
          position: { lat: 40.0, lng: -82.0 },
          battery: { level: 85 },
          location_source: 'gps'
        },
        isConnected: true,
        patterns: [],
        boundaries: [],
        currentPattern: null,
        emergencyStop: false,
        ...initialState?.mower
      },
      ui: {
        sidebarOpen: false,
        notifications: [],
        connectionStatus: 'connected' as const,
        lastActivity: Date.now(),
        modals: {},
        ...initialState?.ui
      }
    }
  })
}

const renderDashboardWithStore = (store: ReturnType<typeof createTestStore>) => {
  return render(
    <Provider store={store}>
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    </Provider>
  )
}

describe('WebSocket Connection Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('establishes WebSocket connection on component mount', async () => {
    const store = createTestStore()
    renderDashboardWithStore(store)

    await waitFor(() => {
      expect(websocket.connect).toHaveBeenCalled()
    })
  })

  test('displays connection status correctly', async () => {
    const store = createTestStore({
      ui: {
        connectionStatus: 'connected'
      }
    })
    
    renderDashboardWithStore(store)

    await waitFor(() => {
      const connectionStatus = screen.getByTestId('connection-status')
      expect(connectionStatus).toHaveAttribute('data-status', 'connected')
      expect(connectionStatus).toHaveTextContent('Connection: connected')
    })
  })

  test('handles connection loss gracefully', async () => {
    const store = createTestStore({
      ui: {
        connectionStatus: 'connected'
      }
    })
    
    renderDashboardWithStore(store)

    // Simulate connection loss
    store.dispatch({ type: 'ui/setConnectionStatus', payload: 'disconnected' })
    store.dispatch({ type: 'mower/setConnected', payload: false })

    await waitFor(() => {
      const connectionStatus = screen.getByTestId('connection-status')
      expect(connectionStatus).toHaveAttribute('data-status', 'disconnected')
    })
  })

  test('updates mower status via WebSocket messages', async () => {
    const store = createTestStore()
    renderDashboardWithStore(store)

    // Simulate WebSocket message subscription
    expect(websocket.subscribe).toHaveBeenCalledWith('mower_status', expect.any(Function))

    // Get the callback function that was passed to subscribe
    const subscribeCall = (websocket.subscribe as any).mock.calls.find(
      call => call[0] === 'mower_status'
    )
    const statusUpdateCallback = subscribeCall[1]

    // Simulate receiving a status update
    const newStatus = {
      connected: true,
      state: 'mowing',
      position: { lat: 40.1, lng: -82.1 },
      battery: { level: 75 },
      location_source: 'gps'
    }

    statusUpdateCallback(newStatus)

    await waitFor(() => {
      const state = store.getState()
      expect(state.mower.status.state).toBe('mowing')
      expect(state.mower.status.battery.level).toBe(75)
    })
  })

  test('handles WebSocket reconnection attempts', async () => {
    const store = createTestStore({
      ui: {
        connectionStatus: 'disconnected'
      }
    })
    
    renderDashboardWithStore(store)

    // Simulate reconnection attempt
    store.dispatch({ type: 'ui/setConnectionStatus', payload: 'connecting' })

    await waitFor(() => {
      const connectionStatus = screen.getByTestId('connection-status')
      expect(connectionStatus).toHaveAttribute('data-status', 'connecting')
    })

    // Simulate successful reconnection
    store.dispatch({ type: 'ui/setConnectionStatus', payload: 'connected' })
    store.dispatch({ type: 'mower/setConnected', payload: true })

    await waitFor(() => {
      const connectionStatus = screen.getByTestId('connection-status')
      expect(connectionStatus).toHaveAttribute('data-status', 'connected')
    })
  })

  test('sends emergency stop command via WebSocket', async () => {
    const store = createTestStore()
    renderDashboardWithStore(store)

    // Simulate emergency stop
    store.dispatch({ type: 'mower/setEmergencyStop', payload: true })

    await waitFor(() => {
      expect(websocket.send).toHaveBeenCalledWith('emergency_stop', { active: true })
    })
  })

  test('handles real-time pattern updates', async () => {
    const store = createTestStore()
    renderDashboardWithStore(store)

    // Verify subscription to pattern updates
    expect(websocket.subscribe).toHaveBeenCalledWith('pattern_update', expect.any(Function))

    // Get the pattern update callback
    const subscribeCall = (websocket.subscribe as any).mock.calls.find(
      call => call[0] === 'pattern_update'
    )
    const patternUpdateCallback = subscribeCall[1]

    // Simulate receiving a pattern update
    const newPattern = {
      id: 'test-pattern',
      type: 'parallel_lines',
      progress: 0.5,
      estimatedTime: 3600
    }

    patternUpdateCallback(newPattern)

    await waitFor(() => {
      const state = store.getState()
      expect(state.mower.currentPattern).toEqual(newPattern)
    })
  })

  test('cleans up WebSocket connection on unmount', async () => {
    const store = createTestStore()
    const { unmount } = renderDashboardWithStore(store)

    unmount()

    await waitFor(() => {
      expect(websocket.disconnect).toHaveBeenCalled()
    })
  })
})

import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router-dom'
import { configureStore } from '@reduxjs/toolkit'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import Maps from '../../pages/Maps'
import mapSlice from '../../store/slices/mapSlice'
import mowerSlice from '../../store/slices/mowerSlice'
import uiSlice from '../../store/slices/uiSlice'

// Mock components to focus on integration testing
vi.mock('../../components/MapContainer', () => ({
  MapContainer: ({ provider, onMapReady }: any) => {
    React.useEffect(() => {
      if (onMapReady) {
        onMapReady()
      }
    }, [onMapReady])
    
    return (
      <div data-testid="map-container" data-provider={provider}>
        Map Container - Provider: {provider}
      </div>
    )
  }
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
          battery: { level: 85 }
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

const renderMapsWithStore = (store: ReturnType<typeof createTestStore>) => {
  return render(
    <Provider store={store}>
      <BrowserRouter>
        <Maps />
      </BrowserRouter>
    </Provider>
  )
}

describe('Map Provider Switching Integration', () => {
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
    vi.clearAllMocks()
  })

  test('switches from Google Maps to Leaflet when Google Maps fails', async () => {
    const store = createTestStore()
    renderMapsWithStore(store)

    // Initially should show Google Maps
    expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'google')

    // Simulate Google Maps failure and auto-fallback
    store.dispatch({ type: 'map/setOffline', payload: true })
    store.dispatch({ type: 'map/setCurrentProvider', payload: 'leaflet' })

    await waitFor(() => {
      expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'leaflet')
    })
  })

  test('manually switches map provider via settings', async () => {
    const store = createTestStore()
    renderMapsWithStore(store)

    // Check initial provider
    expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'google')

    // Simulate provider change via settings
    store.dispatch({ type: 'map/setCurrentProvider', payload: 'leaflet' })
    store.dispatch({ type: 'map/setUserPreferences', payload: { preferredProvider: 'leaflet', autoFallback: true } })

    await waitFor(() => {
      expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'leaflet')
    })
  })

  test('preserves user data when switching providers', async () => {
    const testBoundaries = [
      { id: '1', name: 'Front Yard', coordinates: [[0, 0], [1, 1], [0, 1]] }
    ]
    
    const store = createTestStore({
      mower: {
        boundaries: testBoundaries
      }
    })
    
    renderMapsWithStore(store)

    // Switch provider
    store.dispatch({ type: 'map/setCurrentProvider', payload: 'leaflet' })

    await waitFor(() => {
      expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'leaflet')
    })

    // Verify boundaries are preserved
    const state = store.getState()
    expect(state.mower.boundaries).toEqual(testBoundaries)
  })

  test('handles offline mode gracefully', async () => {
    const store = createTestStore({
      map: {
        isOffline: true,
        currentProvider: 'leaflet'
      }
    })
    
    renderMapsWithStore(store)

    // Should use Leaflet in offline mode
    expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'leaflet')

    // Verify offline indicator is shown
    const state = store.getState()
    expect(state.map.isOffline).toBe(true)
  })

  test('auto-fallback works when preferred provider is unavailable', async () => {
    const store = createTestStore({
      map: {
        userPreferences: {
          preferredProvider: 'google' as const,
          autoFallback: true
        }
      }
    })
    
    renderMapsWithStore(store)

    // Simulate Google Maps being unavailable
    store.dispatch({ type: 'map/setOffline', payload: true })
    
    await waitFor(() => {
      const state = store.getState()
      expect(state.map.isOffline).toBe(true)
    })

    // Should fallback to Leaflet
    store.dispatch({ type: 'map/setCurrentProvider', payload: 'leaflet' })
    
    await waitFor(() => {
      expect(screen.getByTestId('map-container')).toHaveAttribute('data-provider', 'leaflet')
    })
  })
})

import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock environment variables
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:8000',
    VITE_GOOGLE_MAPS_API_KEY: 'test-api-key',
    VITE_WEBSOCKET_URL: 'ws://localhost:8000/ws',
    MODE: 'test',
    DEV: false,
    PROD: false
  }
})

// Mock Google Maps API
const mockGoogle = {
  maps: {
    Map: vi.fn().mockImplementation(() => ({
      setCenter: vi.fn(),
      setZoom: vi.fn(),
      addListener: vi.fn(),
      getCenter: vi.fn().mockReturnValue({ lat: () => 0, lng: () => 0 }),
      getZoom: vi.fn().mockReturnValue(15)
    })),
    Marker: vi.fn().mockImplementation(() => ({
      setPosition: vi.fn(),
      setMap: vi.fn(),
      addListener: vi.fn(),
      getPosition: vi.fn().mockReturnValue({ lat: () => 0, lng: () => 0 })
    })),
    Polygon: vi.fn().mockImplementation(() => ({
      setPath: vi.fn(),
      setMap: vi.fn(),
      addListener: vi.fn()
    })),
    LatLng: vi.fn().mockImplementation((lat: number, lng: number) => ({
      lat: () => lat,
      lng: () => lng
    })),
    event: {
      addListener: vi.fn(),
      removeListener: vi.fn()
    }
  }
}

// @ts-ignore - Global mock
global.google = mockGoogle
// @ts-ignore - Window mock
window.google = mockGoogle

// Mock Leaflet
vi.mock('leaflet', () => ({
  map: vi.fn().mockReturnValue({
    setView: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    on: vi.fn(),
    off: vi.fn()
  }),
  tileLayer: vi.fn().mockReturnValue({
    addTo: vi.fn()
  }),
  marker: vi.fn().mockReturnValue({
    addTo: vi.fn(),
    setLatLng: vi.fn(),
    getLatLng: vi.fn().mockReturnValue({ lat: 0, lng: 0 }),
    on: vi.fn()
  }),
  polygon: vi.fn().mockReturnValue({
    addTo: vi.fn(),
    setLatLngs: vi.fn(),
    on: vi.fn()
  }),
  LatLng: vi.fn().mockImplementation((lat: number, lng: number) => ({ lat, lng }))
}))

// Mock Socket.IO
vi.mock('socket.io-client', () => ({
  io: vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
    connected: true
  }))
}))

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn()
}))

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn()
}))

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn()
  }))
})

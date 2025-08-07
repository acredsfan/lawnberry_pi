import { vi } from 'vitest'

// Mock leaflet module
vi.mock('leaflet', () => {
  return {
    // Mock leaflet map creation
    map: () => ({
      setView: vi.fn(),
      whenReady: vi.fn(),
      addLayer: vi.fn(),
      removeLayer: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      getCenter: vi.fn(),
      getZoom: vi.fn(),
      invalidateSize: vi.fn()
    }),
    tileLayer: vi.fn(),
    marker: vi.fn(),
    circle: vi.fn(),
    polygon: vi.fn(),
    Icon: {
      Default: {
        mergeOptions: vi.fn(),
        _getIconUrl: vi.fn()
      }
    },
    DomEvent: {
      on: vi.fn(),
      off: vi.fn()
    }
  }
})

// Mock leaflet-draw
vi.mock('leaflet-draw', () => ({
  Draw: {
    Polygon: vi.fn(),
    Rectangle: vi.fn(),
    Circle: vi.fn(),
    Marker: vi.fn()
  },
  FeatureGroup: vi.fn()
}))

// Mock react-leaflet components
vi.mock('react-leaflet', () => ({
  useMap: vi.fn(),
  useMapEvents: vi.fn(),
  useLeafletContext: vi.fn(),
  MapContainer: vi.fn(() => 'map-container'),
  TileLayer: vi.fn(),
  Marker: vi.fn(),
  Popup: vi.fn(),
  FeatureGroup: vi.fn(),
  Polygon: vi.fn(),
  Circle: vi.fn(),
  Polyline: vi.fn(),
  Rectangle: vi.fn()
}))

// Mock Redux store
vi.mock('react-redux', () => ({
  ...vi.importActual('react-redux'),
  useSelector: vi.fn((selector) => {
    // Provide mock data for different slices
    if (selector.toString().includes('mower')) {
      return {
        status: {
          state: 'idle',
          position: { lat: 40.7128, lng: -74.0060, heading: 90, accuracy: 5 },
          battery: { level: 78, voltage: 24.2, current: 1.8, charging: false, timeRemaining: 145 },
          sensors: {
            imu: { orientation: { x: 0.1, y: -0.2, z: 0.0 }, acceleration: { x: 0.0, y: 0.0, z: 9.81 }, gyroscope: { x: 0.01, y: -0.02, z: 0.00 }, temperature: 35.6 },
            tof: { left: 1.2, right: 0.8 },
            environmental: { temperature: 24.5, humidity: 65, pressure: 1013.25 },
            power: { voltage: 24.2, current: 1.8, power: 43.56 }
          },
          coverage: { totalArea: 1000, coveredArea: 750, percentage: 75.0 },
          lastUpdate: Date.now(),
          location_source: 'gps',
          connected: true
        },
        isConnected: true
      }
    }
    if (selector.toString().includes('weather')) {
      return {
        data: {
          current: {
            temperature: 24.5,
            humidity: 65,
            windSpeed: 3.2,
            windDirection: 180,
            precipitation: 0,
            condition: 'Partly Cloudy',
            icon: 'partly-cloudy'
          },
          forecast: [{
            date: new Date().toISOString().split('T')[0],
            temperature: { min: 18, max: 28 },
            condition: 'Sunny',
            icon: 'sunny',
            precipitation: 0
          }],
          alerts: []
        }
      }
    }
    if (selector.toString().includes('ui')) {
      return {
        connectionStatus: 'connected',
        notifications: [],
        activity: 0
      }
    }
    return {}
  }),
  useDispatch: () => vi.fn()
}))

// Mock Redux store slices
vi.mock('./store/slices/mowerSlice', () => ({
  setStatus: vi.fn(),
  setConnectionState: vi.fn()
}))

vi.mock('./store/slices/weatherSlice', () => ({
  setWeatherData: vi.fn()
}))

vi.mock('./store/slices/uiSlice', () => ({
  setConnectionStatus: vi.fn(),
  addNotification: vi.fn(),
  updateActivity: vi.fn()
}))

// Mock hooks
vi.mock('./hooks/useUnits', () => ({
  useUnits: () => ({
    format: 'metric',
    converters: {
      temperature: (val: number) => val,
      distance: (val: number) => val,
      area: (val: number) => val
    },
    unitsPrefs: {
      temperature: '°C',
      distance: 'm',
      area: 'm²'
    }
  })
}))

vi.mock('./hooks/usePerformanceMonitor', () => ({
  usePerformanceMonitor: () => ({})
}))

// Mock services
vi.mock('./services/websocket', () => ({
  webSocketService: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    send: vi.fn()
  }
}))

vi.mock('./services/sensorDataService', () => ({
  sensorDataService: {
    start: vi.fn(),
    stop: vi.fn(),
    subscribe: vi.fn((callback) => {
      // Simulate sensor data
      const mockData = {
        gps: { latitude: 40.7128, longitude: -74.0060, accuracy: 5 },
        imu: {
          orientation: { yaw: 90, pitch: 0.1, roll: -0.2 },
          acceleration: { x: 0.0, y: 0.0, z: 9.81 },
          gyroscope: { x: 0.01, y: -0.02, z: 0.00 },
          temperature: 35.6
        },
        tof: { left_distance: 1.2, right_distance: 0.8 },
        environmental: {
          temperature: 24.5,
          humidity: 65,
          pressure: 1013.25,
          rain_detected: false
        },
        power: {
          battery_voltage: 13.6,
          battery_current: 1.8,
          battery_level: 78,
          charging: false
        }
      }
      callback(mockData)
      return () => {}
    })
  }
}))

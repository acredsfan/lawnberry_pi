import React from 'react';
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { BrowserRouter } from 'react-router-dom';
import { configureStore } from '@reduxjs/toolkit';
import Maps from '../Maps';
import mapSlice from '../../store/slices/mapSlice';
import mowerSlice from '../../store/slices/mowerSlice';
import uiSlice from '../../store/slices/uiSlice';

// Mock the MapContainer component since it requires Google Maps API
jest.mock('../../components/MapContainer', () => ({
  MapContainer: () => <div data-testid="map-container">Mock Map Container</div>
}));

// Mock all the editor components
jest.mock('../../components/BoundaryEditor', () => ({
  BoundaryEditor: () => <div data-testid="boundary-editor">Boundary Editor</div>,
  LeafletBoundaryEditor: () => <div data-testid="leaflet-boundary-editor">Leaflet Boundary Editor</div>
}));

jest.mock('../../components/NoGoZoneEditor', () => ({
  NoGoZoneEditor: () => <div data-testid="no-go-zone-editor">No-Go Zone Editor</div>,
  LeafletNoGoZoneEditor: () => <div data-testid="leaflet-no-go-zone-editor">Leaflet No-Go Zone Editor</div>
}));

jest.mock('../../components/HomeLocationManager', () => ({
  HomeLocationManager: () => <div data-testid="home-location-manager">Home Location Manager</div>
}));

jest.mock('../../components/HomeLocationManager/LeafletHomeLocationManager', () => ({
  __esModule: true,
  default: () => <div data-testid="leaflet-home-location-manager">Leaflet Home Location Manager</div>
}));

jest.mock('../../components/PatternVisualizer', () => ({
  PatternVisualizer: () => <div data-testid="pattern-visualizer">Pattern Visualizer</div>
}));

jest.mock('../../components/ProgressTracker', () => ({
  ProgressTracker: () => <div data-testid="progress-tracker">Progress Tracker</div>
}));

// Mock services
jest.mock('../../services/boundaryService', () => ({
  boundaryService: {
    getBoundaries: jest.fn().mockResolvedValue([])
  }
}));

jest.mock('../../services/noGoZoneService', () => ({
  noGoZoneService: {
    getNoGoZones: jest.fn().mockResolvedValue([])
  }
}));

jest.mock('../../services/homeLocationService', () => ({
  homeLocationService: {
    getHomeLocations: jest.fn().mockResolvedValue([]),
    getHomeLocationIcon: jest.fn().mockReturnValue('🏠'),
    getHomeLocationTypeLabel: jest.fn().mockReturnValue('Charging Station')
  }
}));

const createMockStore = () => {
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
        }
      },
      mower: {
        status: {
          connected: true,
          state: 'idle',
          position: { lat: 40.0, lng: -82.0 },
          battery: 85
        },
        isConnected: true,
        patterns: [],
        boundaries: [],
        currentPattern: null,
        emergencyStop: false
      },
      ui: {
        sidebarOpen: false,
        notifications: [],
        connectionStatus: 'connected' as const,
        lastActivity: Date.now(),
        modals: {}
      }
    }
  });
};

describe('Maps Component', () => {
  let store: ReturnType<typeof createMockStore>;

  beforeEach(() => {
    store = createMockStore();
  });

  const renderMaps = () => {
    return render(
      <Provider store={store}>
        <BrowserRouter>
          <Maps />
        </BrowserRouter>
      </Provider>
    );
  };

  test('renders Maps page with title and description', () => {
    renderMaps();
    
    expect(screen.getByText('LawnBerry Maps')).toBeInTheDocument();
    expect(screen.getByText(/Interactive mapping for yard boundary management/)).toBeInTheDocument();
  });

  test('renders all tab navigation options', () => {
    renderMaps();
    
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Boundaries')).toBeInTheDocument();
    expect(screen.getByText('No-Go Zones')).toBeInTheDocument();
    expect(screen.getByText('Home Locations')).toBeInTheDocument();
    expect(screen.getByText('Patterns')).toBeInTheDocument();
  });

  test('displays keyboard shortcut indicators on tabs', () => {
    renderMaps();
    
    // Check for keyboard shortcut chips
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  test('shows robot status information in overview tab', () => {
    renderMaps();
    
    expect(screen.getByText('Robot Status')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument(); // Battery level
    expect(screen.getByText('idle')).toBeInTheDocument(); // Robot state
  });

  test('displays map statistics', () => {
    renderMaps();
    
    expect(screen.getByText('Map Statistics')).toBeInTheDocument();
    expect(screen.getByText('Total Area')).toBeInTheDocument();
    expect(screen.getByText('Boundaries')).toBeInTheDocument();
  });

  test('renders help button', () => {
    renderMaps();
    
    const helpButton = screen.getByLabelText('Show keyboard shortcuts');
    expect(helpButton).toBeInTheDocument();
  });

  test('displays layer toggle controls in overview', () => {
    renderMaps();
    
    expect(screen.getByText('Boundaries')).toBeInTheDocument();
    expect(screen.getByText('No-Go Zones')).toBeInTheDocument();
    expect(screen.getByText('Home Locations')).toBeInTheDocument();
    expect(screen.getByText('Robot Path')).toBeInTheDocument();
  });
});

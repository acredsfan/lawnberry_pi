import React from 'react';
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import mapReducer from '../../../store/slices/mapSlice';
import { MapContainer } from '../index';

// Mock the map service
jest.mock('../../../services/mapService', () => ({
  mapService: {
    getInstance: () => ({
      initializeProvider: jest.fn().mockResolvedValue('openstreetmap'),
      updateConfig: jest.fn(),
      getConfig: jest.fn().mockReturnValue({
        defaultCenter: { lat: 40.7128, lng: -74.0060 },
        defaultZoom: 15,
        usageLevel: 'medium'
      }),
      getUsageLevelSettings: jest.fn().mockReturnValue({
        refreshRate: 5000,
        tileQuality: 'medium',
        enableAllFeatures: true,
        cacheSize: 50
      }),
      createMapError: jest.fn()
    })
  }
}));

// Mock the map components
jest.mock('../GoogleMapComponent', () => {
  return function GoogleMapComponent() {
    return <div data-testid="google-map">Google Map</div>;
  };
});

jest.mock('../LeafletMapComponent', () => {
  return function LeafletMapComponent() {
    return <div data-testid="leaflet-map">Leaflet Map</div>;
  };
});

const createTestStore = () => configureStore({
  reducer: {
    map: mapReducer
  }
});

describe('MapContainer', () => {
  it('renders without crashing', () => {
    const store = createTestStore();
    
    render(
      <Provider store={store}>
        <MapContainer />
      </Provider>
    );
    
    // Should show loading initially
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('supports different usage levels', () => {
    const store = createTestStore();
    
    render(
      <Provider store={store}>
        <MapContainer usageLevel="low" />
      </Provider>
    );
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('accepts custom center and zoom props', () => {
    const store = createTestStore();
    const center = { lat: 37.7749, lng: -122.4194 };
    
    render(
      <Provider store={store}>
        <MapContainer center={center} zoom={12} />
      </Provider>
    );
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });
});

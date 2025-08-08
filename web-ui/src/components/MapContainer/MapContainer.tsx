import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Alert, CircularProgress, ToggleButtonGroup, ToggleButton } from '@mui/material';
import { MapError, MapState, MapUsageLevel } from '../../types';
import { MapProvider } from '../../types';
import { mapService } from '../../services/mapService';
import { useMapAutoCentering } from '../../hooks/useMapAutoCentering';
import GoogleMapComponent from './GoogleMapComponent';
import LeafletMapComponent from './LeafletMapComponent';
import WeatherWidget from '../WeatherWidget';

export interface MapContainerProps {
  center?: { lat: number; lng: number };
  zoom?: number;
  usageLevel?: MapUsageLevel;
  preferredProvider?: MapProvider;
  onProviderChange?: (provider: MapProvider) => void;
  onError?: (error: MapError) => void;
  robotPosition?: { lat: number; lng: number };
  robotPath?: Array<{ lat: number; lng: number }>;
  weather?: {
    temperature: number;
    humidity: number;
    condition: string;
  };
  style?: React.CSSProperties;
  className?: string;
  children?: React.ReactNode;
}

const MapContainer: React.FC<MapContainerProps> = ({
  center,
  zoom = 15,
  usageLevel = 'medium',
  preferredProvider,
  onProviderChange,
  onError,
  robotPosition,
  robotPath,
  weather,
  style,
  className,
  children
}) => {
  const [mapState, setMapState] = useState<MapState>({
    isLoading: true,
    error: null,
    currentProvider: preferredProvider || 'google' as MapProvider,
    isOffline: !navigator.onLine,
    cacheStatus: 'empty'
  });
  
  const [currentCenter, setCurrentCenter] = useState(center);
  const initializationRef = useRef(false);

  // Auto-centering functionality
  const handleCenterRequest = useCallback((position: { lat: number; lng: number }) => {
    console.log('🎯 MapContainer received center request:', position);
    setCurrentCenter(position);
  }, []);

  useMapAutoCentering(handleCenterRequest);

  // Update center when prop changes
  useEffect(() => {
    if (center && center !== currentCenter) {
      setCurrentCenter(center);
    }
  }, [center, currentCenter]);

  const handleError = useCallback((error: MapError) => {
    setMapState(prev => ({ ...prev, error, isLoading: false }));
    onError?.(error);
  }, [onError]);

  const initializeMap = useCallback(async () => {
    if (initializationRef.current) return;
    initializationRef.current = true;

    console.log('🗺️ Initializing MapContainer...');
    setMapState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      // Update map service configuration
      mapService.updateConfig({
        usageLevel,
        defaultCenter: center || mapService.getConfig().defaultCenter,
        defaultZoom: zoom
      });

      // Check Google Maps API key availability
      const apiKey = import.meta.env.REACT_APP_GOOGLE_MAPS_API_KEY;
      console.log('🔑 Google Maps API Key status:', apiKey ? 'Available' : 'Missing');

      // Initialize the preferred provider, with Google as priority if API key is available
      const targetProvider = apiKey ? 'google' : 'openstreetmap';
      const actualProvider = await mapService.initializeProvider(targetProvider);
      
      console.log('📍 Map initialized with provider:', actualProvider);
      
      setMapState({
        isLoading: false,
        error: null,
        currentProvider: actualProvider,
        isOffline: !navigator.onLine,
        cacheStatus: 'partial'
      });

      onProviderChange?.(actualProvider);
    } catch (error) {
      console.error('❌ Map initialization error:', error);
      const mapError = mapService.createMapError(
        'generic',
        error instanceof Error ? error.message : 'Failed to initialize map',
        preferredProvider || 'google' as MapProvider,
        false
      );
      handleError(mapError);
    }
  }, [usageLevel, handleError]); // Removed frequently changing dependencies

  useEffect(() => {
    initializeMap();
  }, []); // Initialize only once

  useEffect(() => {
    const handleOnline = () => setMapState(prev => ({ ...prev, isOffline: false }));
    const handleOffline = () => setMapState(prev => ({ ...prev, isOffline: true }));

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const handleProviderSwitch = useCallback(async (
    _: React.MouseEvent<HTMLElement>,
    newProvider: MapProvider
  ) => {
    if (!newProvider || newProvider === mapState.currentProvider) return;

    setMapState(prev => ({ ...prev, isLoading: true, error: null }));
    initializationRef.current = false;

    try {
      const actualProvider = await mapService.initializeProvider(newProvider);
      setMapState(prev => ({
        ...prev,
        isLoading: false,
        currentProvider: actualProvider
      }));
      onProviderChange?.(actualProvider);
    } catch (error) {
      const mapError = mapService.createMapError(
        'generic',
        error instanceof Error ? error.message : 'Failed to switch provider',
        newProvider,
        true
      );
      handleError(mapError);
    }
  }, [mapState.currentProvider, onProviderChange, handleError]);

  const retryInitialization = useCallback(() => {
    initializationRef.current = false;
    initializeMap();
  }, [initializeMap]);

  if (mapState.isLoading) {
    return (
      <Box
        className={className}
        style={style}
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 400,
          bgcolor: 'grey.100'
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (mapState.error && !mapState.error.canFallback) {
    return (
      <Box className={className} style={style}>
        <Alert 
          severity="error" 
          action={
            <ToggleButtonGroup
              value={mapState.currentProvider}
              exclusive
              onChange={handleProviderSwitch}
              size="small"
            >
              <ToggleButton value="google">Google Maps</ToggleButton>
              <ToggleButton value="openstreetmap">OpenStreetMap</ToggleButton>
            </ToggleButtonGroup>
          }
        >
          {mapState.error.message}
        </Alert>
      </Box>
    );
  }

  const mapProps = {
    center: currentCenter || mapService.getConfig().defaultCenter,
    zoom,
    usageLevel,
    isOffline: mapState.isOffline,
    onError: handleError,
    robotPosition,
    robotPath,
    style: { width: '100%', height: '100%' }
  };

  return (
    <Box 
      className={className} 
      style={style} 
      sx={{ 
        position: 'relative',
        height: '100%',
        width: '100%',
        '& > div:last-child': {
          height: '100%',
          width: '100%'
        }
      }}
    >
      {weather && (
        <WeatherWidget
          weather={weather}
          style={{
            position: 'absolute',
            top: 10,
            left: 10,
            zIndex: 1000,
            backgroundColor: 'rgba(255, 255, 255, 0.8)',
          }}
        />
      )}
      {mapState.error && (
        <Alert 
          severity="warning" 
          sx={{ mb: 1 }}
          onClose={() => setMapState(prev => ({ ...prev, error: null }))}
        >
          {mapState.error.message} - Using fallback provider.
        </Alert>
      )}
      
      <Box sx={{ position: 'absolute', top: 10, right: 10, zIndex: 1000 }}>
        <ToggleButtonGroup
          value={mapState.currentProvider}
          exclusive
          onChange={handleProviderSwitch}
          size="small"
          sx={{ bgcolor: 'white', boxShadow: 1 }}
        >
          <ToggleButton value="google">Google</ToggleButton>
          <ToggleButton value="openstreetmap">OSM</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {mapState.currentProvider === 'google' ? (
        <GoogleMapComponent {...mapProps}>
          {children}
        </GoogleMapComponent>
      ) : (
        <LeafletMapComponent {...mapProps}>
          {children}
        </LeafletMapComponent>
      )}
    </Box>
  );
};

export default MapContainer;

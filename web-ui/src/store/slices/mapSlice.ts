import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { MapProvider, MapConfig, MapError, MapState, MapUsageLevel } from '../../types';

interface MapSliceState extends MapState {
  config: MapConfig;
  lastKnownPosition: { lat: number; lng: number } | null;
  userPreferences: {
    preferredProvider: MapProvider;
    autoFallback: boolean;
    showProviderSwitch: boolean;
  };
}

const initialState: MapSliceState = {
  // Map state
  isLoading: false,
  error: null,
  currentProvider: 'google',
  isOffline: false,
  cacheStatus: 'empty',
  
  // Map configuration
  config: {
    provider: 'google',
    usageLevel: 'medium',
    apiKey: undefined,
    defaultCenter: { lat: 40.7128, lng: -74.0060 },
    defaultZoom: 15,
    enableCaching: true,
    offlineMode: false
  },
  
  // Additional state
  lastKnownPosition: null,
  userPreferences: {
    preferredProvider: 'google',
    autoFallback: true,
    showProviderSwitch: true
  }
};

const mapSlice = createSlice({
  name: 'map',
  initialState,
  reducers: {
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload;
    },
    
    setError: (state, action: PayloadAction<MapError | null>) => {
      state.error = action.payload;
      if (action.payload) {
        state.isLoading = false;
      }
    },
    
    setCurrentProvider: (state, action: PayloadAction<MapProvider>) => {
      state.currentProvider = action.payload;
      state.error = null; // Clear errors when provider changes successfully
    },
    
    setOfflineStatus: (state, action: PayloadAction<boolean>) => {
      state.isOffline = action.payload;
    },
    
    setCacheStatus: (state, action: PayloadAction<'empty' | 'partial' | 'full'>) => {
      state.cacheStatus = action.payload;
    },
    
    updateConfig: (state, action: PayloadAction<Partial<MapConfig>>) => {
      state.config = { ...state.config, ...action.payload };
    },
    
    setUsageLevel: (state, action: PayloadAction<MapUsageLevel>) => {
      state.config.usageLevel = action.payload;
    },
    
    setDefaultCenter: (state, action: PayloadAction<{ lat: number; lng: number }>) => {
      state.config.defaultCenter = action.payload;
    },
    
    setDefaultZoom: (state, action: PayloadAction<number>) => {
      state.config.defaultZoom = action.payload;
    },
    
    setLastKnownPosition: (state, action: PayloadAction<{ lat: number; lng: number } | null>) => {
      state.lastKnownPosition = action.payload;
    },
    
    setPreferredProvider: (state, action: PayloadAction<MapProvider>) => {
      state.userPreferences.preferredProvider = action.payload;
      state.config.provider = action.payload;
    },
    
    setAutoFallback: (state, action: PayloadAction<boolean>) => {
      state.userPreferences.autoFallback = action.payload;
    },
    
    setShowProviderSwitch: (state, action: PayloadAction<boolean>) => {
      state.userPreferences.showProviderSwitch = action.payload;
    },
    
    resetMapState: (state) => {
      state.isLoading = false;
      state.error = null;
      state.cacheStatus = 'empty';
    },
    
    initializeMapFromEnvironment: (state) => {
      // This would typically be called on app initialization
      const apiKey = import.meta.env.REACT_APP_GOOGLE_MAPS_API_KEY;
      if (apiKey) {
        state.config.apiKey = apiKey;
        state.config.provider = 'google';
        state.userPreferences.preferredProvider = 'google';
      } else {
        state.config.provider = 'openstreetmap';
        state.userPreferences.preferredProvider = 'openstreetmap';
      }
    }
  }
});

export const {
  setLoading,
  setError,
  setCurrentProvider,
  setOfflineStatus,
  setCacheStatus,
  updateConfig,
  setUsageLevel,
  setDefaultCenter,
  setDefaultZoom,
  setLastKnownPosition,
  setPreferredProvider,
  setAutoFallback,
  setShowProviderSwitch,
  resetMapState,
  initializeMapFromEnvironment
} = mapSlice.actions;

export default mapSlice.reducer;

// Selectors
export const selectMapState = (state: { map: MapSliceState }) => state.map;
export const selectMapConfig = (state: { map: MapSliceState }) => state.map.config;
export const selectMapError = (state: { map: MapSliceState }) => state.map.error;
export const selectCurrentProvider = (state: { map: MapSliceState }) => state.map.currentProvider;
export const selectUserPreferences = (state: { map: MapSliceState }) => state.map.userPreferences;
export const selectLastKnownPosition = (state: { map: MapSliceState }) => state.map.lastKnownPosition;

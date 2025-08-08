import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { 
  Box, 
  Typography, 
  Paper, 
  FormControl, 
  InputLabel, 
  Select, 
  MenuItem,
  Switch,
  FormControlLabel,
  Alert,
  Tabs,
  Tab,
  Grid,
  Card,
  CardContent,
  Chip,
  Tooltip,
  Fab,
  useTheme,
  useMediaQuery
} from '@mui/material';
import { 
  Map as MapIcon, 
  LocationOn as LocationIcon,
  Block as BlockIcon,
  Home as HomeIcon,
  Timeline as TimelineIcon,
  Help as HelpIcon,
  Fullscreen as FullscreenIcon,
  FullscreenExit as FullscreenExitIcon
} from '@mui/icons-material';
import { MapContainer } from '../components/MapContainer';
import { BoundaryEditor, LeafletBoundaryEditor } from '../components/BoundaryEditor';
import { NoGoZoneEditor, LeafletNoGoZoneEditor } from '../components/NoGoZoneEditor';
import { HomeLocationManager } from '../components/HomeLocationManager';
import LeafletHomeLocationManager from '../components/HomeLocationManager/LeafletHomeLocationManager';
import { PatternVisualizer } from '../components/PatternVisualizer';
import { ProgressTracker } from '../components/ProgressTracker';
import { 
  selectMapState, 
  selectMapConfig, 
  selectUserPreferences,
  setUsageLevel,
  setPreferredProvider,
  setAutoFallback,
  initializeMapFromEnvironment
} from '../store/slices/mapSlice';
import { setCurrentPattern } from '../store/slices/mowerSlice';
import { RootState, AppDispatch } from '../store/store';
import { MapUsageLevel, MapProvider } from '../types';
import { boundaryService, Boundary } from '../services/boundaryService';
import { noGoZoneService, NoGoZone } from '../services/noGoZoneService';
import { homeLocationService, HomeLocation } from '../services/homeLocationService';
import { useUnits } from '../hooks/useUnits';

const Maps: React.FC = () => {
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up('lg'));
  const dispatch = useDispatch<AppDispatch>();
  const mapState = useSelector((state: RootState) => selectMapState(state));
  const mapConfig = useSelector((state: RootState) => selectMapConfig(state));
  const userPreferences = useSelector((state: RootState) => selectUserPreferences(state));
  const { status } = useSelector((state: RootState) => state.mower);
  const { format: formatUnits } = useUnits();

  const [activeTab, setActiveTab] = useState(0);
  const [boundaries, setBoundaries] = useState<Boundary[]>([]);
  const [noGoZones, setNoGoZones] = useState<NoGoZone[]>([]);
  const [homeLocations, setHomeLocations] = useState<HomeLocation[]>([]);
  const [showHelp, setShowHelp] = useState(false);
  const mapRef = useRef<google.maps.Map | L.Map | null>(null);

  // Determine if we should use full-width layout (desktop full-page mode); allow user toggle
  const [useFullWidth, setUseFullWidth] = useState(isDesktop);

  const robotPosition = status?.position ? {
    lat: status.position.lat,
    lng: status.position.lng
  } : undefined;

  // Keyboard shortcuts
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Only handle shortcuts when not typing in input fields
    if (event.target && (event.target as HTMLElement).tagName.toLowerCase() === 'input') {
      return;
    }

    switch (event.key) {
      case '1':
        setActiveTab(0);
        break;
      case '2':
        setActiveTab(1);
        break;
      case '3':
        setActiveTab(2);
        break;
      case '4':
        setActiveTab(3);
        break;
      case '5':
        setActiveTab(4);
        break;
      case 'h':
      case 'H':
        setShowHelp(!showHelp);
        break;
      case 'Escape':
        setShowHelp(false);
        break;
    }
  }, [showHelp]);

  useEffect(() => {
    // Initialize map configuration from environment on component mount
    console.log('🗺️ Maps page initializing...');
    console.log('🔑 Environment check:', {
      viteKey: import.meta.env.VITE_REACT_APP_GOOGLE_MAPS_API_KEY ? 'Found' : 'Not found',
      reactKey: import.meta.env.REACT_APP_GOOGLE_MAPS_API_KEY ? 'Found' : 'Not found',
      processKey: process.env.REACT_APP_GOOGLE_MAPS_API_KEY ? 'Found' : 'Not found'
    });
    
    // Initialize with Google Maps as preferred if API key is available
    const hasGoogleApiKey = !!(
      import.meta.env.REACT_APP_GOOGLE_MAPS_API_KEY || 
      import.meta.env.VITE_REACT_APP_GOOGLE_MAPS_API_KEY ||
      process.env.REACT_APP_GOOGLE_MAPS_API_KEY
    );
    
    if (hasGoogleApiKey) {
      dispatch(setPreferredProvider('google'));
      console.log('✅ Google Maps API key found - setting Google as preferred provider');
    } else {
      dispatch(setPreferredProvider('openstreetmap'));
      console.log('⚠️ No Google Maps API key - falling back to OpenStreetMap');
    }
    
    dispatch(initializeMapFromEnvironment());
    loadBoundaries();
    loadNoGoZones();
    loadHomeLocations();

    // Add keyboard event listeners
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [dispatch, handleKeyDown]);

  const loadBoundaries = async () => {
    try {
      const loadedBoundaries = await boundaryService.getBoundaries();
      setBoundaries(loadedBoundaries);
    } catch (error) {
      console.error('Failed to load boundaries:', error);
    }
  };

  const loadNoGoZones = async () => {
    try {
      const loadedZones = await noGoZoneService.getNoGoZones();
      setNoGoZones(loadedZones);
    } catch (error) {
      console.error('Failed to load no-go zones:', error);
    }
  };

  const loadHomeLocations = async () => {
    try {
      const loadedLocations = await homeLocationService.getHomeLocations();
      setHomeLocations(loadedLocations);
    } catch (error) {
      console.error('Failed to load home locations:', error);
    }
  };

  const handleBoundariesChange = (updatedBoundaries: Boundary[]) => {
    setBoundaries(updatedBoundaries);
  };

  const handleNoGoZonesChange = (updatedZones: NoGoZone[]) => {
    setNoGoZones(updatedZones);
  };

  const handleHomeLocationsChange = (updatedLocations: HomeLocation[]) => {
    setHomeLocations(updatedLocations);
  };

  const handlePatternChange = (pattern: string, parameters: any) => {
    dispatch(setCurrentPattern(pattern));
  };

  const handlePreviewStart = (pattern: string) => {
    // Navigate to Navigation page or start mowing
    console.log('Starting mowing with pattern:', pattern);
  };

  const handleUsageLevelChange = (level: MapUsageLevel) => {
    dispatch(setUsageLevel(level));
  };

  const handleProviderChange = (provider: MapProvider) => {
    dispatch(setPreferredProvider(provider));
  };

  const handleAutoFallbackChange = (enabled: boolean) => {
    dispatch(setAutoFallback(enabled));
  };

  const validBoundaries = boundaries.filter(b => b.isValid);
  const invalidBoundaries = boundaries.filter(b => !b.isValid);
  const defaultHomeLocation = homeLocations.find(l => l.is_default);
  const totalArea = boundaries.reduce((sum, b) => sum + (b.area || 0), 0);
  const activeNoGoZones = noGoZones.filter(z => z.isEnabled && z.isValid);
  const totalNoGoArea = noGoZones.reduce((sum, z) => sum + (z.area || 0), 0);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        LawnBerry Maps
      </Typography>
      
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Interactive mapping for yard boundary management, mowing patterns, and robot navigation.
      </Typography>

      {/* API Key Status */}
      {mapState.error && mapState.error.type === 'api_key_invalid' && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Google Maps API key not configured. Using OpenStreetMap as fallback. 
          Configure REACT_APP_GOOGLE_MAPS_API_KEY in your environment to enable Google Maps.
        </Alert>
      )}

      {mapState.currentProvider === 'openstreetmap' && !mapState.error && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Using OpenStreetMap provider. Google Maps is available if you configure REACT_APP_GOOGLE_MAPS_API_KEY.
        </Alert>
      )}

      {mapState.error && mapState.error.type !== 'api_key_invalid' && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Map Error: {mapState.error.message}
        </Alert>
      )}

      <Paper>
        <Tabs
          value={activeTab}
          onChange={(e, newValue) => setActiveTab(newValue)}
          aria-label="maps tabs"
        >
          <Tab 
            icon={<MapIcon />} 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                Overview
                <Chip label="1" size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: '16px', minWidth: '16px' }} />
              </Box>
            }
          />
          <Tab 
            icon={<LocationIcon />} 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                Boundaries
                <Chip label="2" size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: '16px', minWidth: '16px' }} />
              </Box>
            }
          />
          <Tab 
            icon={<BlockIcon />} 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                No-Go Zones
                <Chip label="3" size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: '16px', minWidth: '16px' }} />
              </Box>
            }
          />
          <Tab 
            icon={<HomeIcon />} 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                Home Locations
                <Chip label="4" size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: '16px', minWidth: '16px' }} />
              </Box>
            }
          />
          <Tab 
            icon={<TimelineIcon />} 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                Patterns
                <Chip label="5" size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: '16px', minWidth: '16px' }} />
              </Box>
            }
          />
        </Tabs>

        <Box sx={{ p: useFullWidth ? 0 : 3 }}>
          {activeTab === 0 && (
            // Render the map full‑width and stack the statistics below it
            <Grid container spacing={useFullWidth ? 0 : 3} direction="column">
              {/* Map row: always full width */}
              <Grid item xs={12}>
                <Paper sx={{ 
                  height: useFullWidth ? 'calc(100vh - 120px)' : isDesktop ? '75vh' : '60vh', 
                  minHeight: '500px',
                  overflow: 'hidden', 
                  position: 'relative',
                  borderRadius: useFullWidth ? 0 : 1
                }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    style={{ height: '100%' }}
                  >
                    {/* TODO: Add boundary, no-go zone, and home location components as children */}
                  </MapContainer>
                  
                  {/* Layer toggle controls */}
                  <Box
                    sx={{
                      position: 'absolute',
                      // Position toggles in bottom‑right so they don’t overlap map controls
                      bottom: 16,
                      right: 16,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 1,
                      backgroundColor: 'background.paper',
                      p: 1,
                      borderRadius: 1,
                      boxShadow: 2,
                      zIndex: 1000
                    }}
                  >
                    <FormControlLabel
                      control={<Switch size="small" defaultChecked />}
                      label="Boundaries"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" defaultChecked />}
                      label="No-Go Zones"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" defaultChecked />}
                      label="Home Locations"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" defaultChecked />}
                      label="Robot Path"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                  </Box>
                </Paper>
              </Grid>

              {/* Statistics row: render below the map */}
              <Grid item xs={12}>
                <Grid container spacing={2}>
                    {/* Robot Status Card */}
                    <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Box
                            sx={{
                              width: 12,
                              height: 12,
                              borderRadius: '50%',
                              backgroundColor: status?.connected ? 'success.main' : 'error.main'
                            }}
                          />
                          Robot Status
                        </Typography>
                        
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="body2" color="text.secondary">
                            Current State
                          </Typography>
                          <Chip
                            label={status?.state || 'Unknown'}
                            color={status?.state === 'mowing' ? 'success' : status?.state === 'charging' ? 'info' : 'default'}
                            size="small"
                          />
                        </Box>

                        {robotPosition && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="body2" color="text.secondary">
                              Current Position
                            </Typography>
                            <Typography variant="body2">
                              {robotPosition.lat.toFixed(6)}, {robotPosition.lng.toFixed(6)}
                            </Typography>
                          </Box>
                        )}

                        {typeof status?.battery?.level === 'number' && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="body2" color="text.secondary">
                              Battery Level
                            </Typography>
                            <Typography variant="h4" sx={{ color: status?.battery?.level < 20 ? 'error.main' : 'inherit' }}>
                              {status?.battery?.level.toFixed(1)}%
                            </Typography>
                          </Box>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Map Statistics Card */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>
                          Map Statistics
                        </Typography>
                        
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="body2" color="text.secondary">
                            Total Area
                          </Typography>
                          <Typography variant="h4">
                            {formatUnits.area(totalArea)}
                          </Typography>
                        </Box>

                        <Box sx={{ mb: 2 }}>
                          <Typography variant="body2" color="text.secondary">
                            Boundaries
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                            <Chip
                              label={`${validBoundaries.length} Valid`}
                              color="success"
                              size="small"
                            />
                            {invalidBoundaries.length > 0 && (
                              <Chip
                                label={`${invalidBoundaries.length} Invalid`}
                                color="error"
                                size="small"
                              />
                            )}
                          </Box>
                        </Box>

                        <Box sx={{ mb: 2 }}>
                          <Typography variant="body2" color="text.secondary">
                            No-Go Zones
                          </Typography>
                          <Typography variant="body1">
                            {activeNoGoZones.length} active ({formatUnits.area(totalNoGoArea)})
                          </Typography>
                        </Box>

                        <Box sx={{ mb: 2 }}>
                          <Typography variant="body2" color="text.secondary">
                            Home Locations
                          </Typography>
                          <Typography variant="body1">
                            {homeLocations.length} configured
                          </Typography>
                        </Box>

                        <Typography variant="body2" color="text.secondary">
                          Map Provider: <strong>{mapState.currentProvider}</strong>
                          {mapConfig.apiKey && <> (API Key: Configured)</>}
                          {mapState.isOffline && <> - OFFLINE MODE</>}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Progress Tracking Card - only show when mowing */}
                  {status?.state === 'mowing' && (
                    <Grid item xs={12}>
                      <ProgressTracker
                        mapProvider={userPreferences.preferredProvider}
                        map={mapRef.current}
                        robotPosition={robotPosition}
                      />
                    </Grid>
                  )}
                </Grid>
                </Grid>
              </Grid>
            </Grid>
          )}

          {activeTab === 1 && (
            <Grid container spacing={3}>
              <Grid item xs={12} lg={8}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>
              
              <Grid item xs={12} lg={4}>
                {userPreferences.preferredProvider === 'google' ? (
                  <BoundaryEditor
                    map={mapRef.current as google.maps.Map}
                    boundaries={boundaries}
                    onBoundariesChange={handleBoundariesChange}
                    robotPosition={robotPosition}
                  />
                ) : (
                  <LeafletBoundaryEditor
                    map={mapRef.current as L.Map}
                    boundaries={boundaries}
                    onBoundariesChange={handleBoundariesChange}
                    robotPosition={robotPosition}
                  />
                )}
              </Grid>
            </Grid>
          )}

          {activeTab === 2 && (
            <Grid container spacing={3}>
              <Grid item xs={12} lg={8}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>
              
              <Grid item xs={12} lg={4}>
                {userPreferences.preferredProvider === 'google' ? (
                  <NoGoZoneEditor
                    map={mapRef.current as google.maps.Map}
                    noGoZones={noGoZones}
                    onNoGoZonesChange={handleNoGoZonesChange}
                    yardBoundaries={boundaries.filter(b => b.isValid).map(b => b.points)}
                    robotPosition={robotPosition}
                  />
                ) : (
                  <LeafletNoGoZoneEditor
                    map={mapRef.current as L.Map}
                    noGoZones={noGoZones}
                    onNoGoZonesChange={handleNoGoZonesChange}
                    yardBoundaries={boundaries.filter(b => b.isValid).map(b => b.points)}
                    robotPosition={robotPosition}
                  />
                )}
              </Grid>
            </Grid>
          )}

          {activeTab === 3 && (
            <Grid container spacing={3}>
              <Grid item xs={12} lg={8}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>
              
              <Grid item xs={12} lg={4}>
                {userPreferences.preferredProvider === 'google' ? (
                  <HomeLocationManager
                    map={mapRef.current as google.maps.Map}
                    yardBoundaries={boundaries.filter(b => b.isValid).map(b => b.points)}
                    robotPosition={robotPosition}
                    onHomeLocationsChange={handleHomeLocationsChange}
                  />
                ) : (
                  <LeafletHomeLocationManager
                    map={mapRef.current as L.Map}
                    yardBoundaries={boundaries.filter(b => b.isValid).map(b => b.points)}
                    robotPosition={robotPosition}
                    onHomeLocationsChange={handleHomeLocationsChange}
                  />
                )}
              </Grid>
            </Grid>
          )}

          {activeTab === 4 && (
            <Grid container spacing={3}>
              <Grid item xs={12} lg={8}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>
              
              <Grid item xs={12} lg={4}>
                <PatternVisualizer
                  mapInstance={mapRef.current}
                  mapProvider={userPreferences.preferredProvider}
                  boundaries={boundaries.length > 0 ? boundaries[0]?.points || [] : []}
                  noGoZones={noGoZones.map(zone => zone.points)}
                  onPatternChange={handlePatternChange}
                  onPreviewStart={handlePreviewStart}
                />
              </Grid>
            </Grid>
          )}
        </Box>
      </Paper>

      {/* Fullscreen Toggle FAB */}
      <Fab
        color="primary"
        aria-label="toggle fullscreen"
        onClick={() => setUseFullWidth(!useFullWidth)}
        sx={{
          position: 'fixed',
          bottom: 16,
          right: 16,
          zIndex: 1000
        }}
      >
        {useFullWidth ? <FullscreenExitIcon /> : <FullscreenIcon />}
      </Fab>
    </Box>
  );
};

export default Maps;

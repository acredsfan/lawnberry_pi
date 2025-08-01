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
  Fab
} from '@mui/material';
import { 
  Map as MapIcon, 
  LocationOn as LocationIcon,
  Block as BlockIcon,
  Home as HomeIcon,
  Timeline as TimelineIcon,
  Help as HelpIcon
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

const Maps: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const mapState = useSelector((state: RootState) => selectMapState(state));
  const mapConfig = useSelector((state: RootState) => selectMapConfig(state));
  const userPreferences = useSelector((state: RootState) => selectUserPreferences(state));
  const { status } = useSelector((state: RootState) => state.mower);

  const [activeTab, setActiveTab] = useState(0);
  const [boundaries, setBoundaries] = useState<Boundary[]>([]);
  const [noGoZones, setNoGoZones] = useState<NoGoZone[]>([]);
  const [homeLocations, setHomeLocations] = useState<HomeLocation[]>([]);
  const [showHelp, setShowHelp] = useState(false);
  const mapRef = useRef<google.maps.Map | L.Map | null>(null);

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
      {!mapConfig.apiKey && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Google Maps API key not configured. Using OpenStreetMap as fallback. 
          Configure REACT_APP_GOOGLE_MAPS_API_KEY in your environment to enable Google Maps.
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

        <Box sx={{ p: 3 }}>
          {activeTab === 0 && (
            <Grid container spacing={3}>
              <Grid item xs={12} lg={8}>
                <Paper sx={{ height: 600, overflow: 'hidden', position: 'relative' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
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
                      top: 16,
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
              
              <Grid item xs={12} lg={4}>
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

                        {status?.battery !== undefined && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="body2" color="text.secondary">
                              Battery Level
                            </Typography>
                            <Typography variant="h4" color={status.battery.level < 20 ? 'error.main' : 'inherit'}>
                              {status.battery.level}%
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
                            {totalArea < 1000 ? `${Math.round(totalArea)} m²` : `${(totalArea / 10000).toFixed(2)} ha`}
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
                            {activeNoGoZones.length} active ({totalNoGoArea < 1000 ? `${Math.round(totalNoGoArea)} m²` : `${(totalNoGoArea / 10000).toFixed(2)} ha`})
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
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    style={{ height: '100%' }}
                    onMapReady={(map) => {
                      mapRef.current = map;
                    }}
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
    </Box>
  );
};

export default Maps;

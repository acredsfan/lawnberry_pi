import React, { useEffect, useState, useRef, useCallback } from 'react';
import L from 'leaflet';
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
  initializeMapFromEnvironment,
  setError,
  updateConfig
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
  const handleMapReady = useCallback(
    (mapInstance: any) => {
      mapRef.current = mapInstance;

      boundaries.forEach(boundary => {
        if (mapInstance && (mapInstance as any).addLayer) {
          L.polygon(boundary.points).addTo(mapInstance as any);
        }
      });

      noGoZones.forEach(zone => {
        if (mapInstance && (mapInstance as any).addLayer) {
          L.polygon(zone.points, { color: 'red' }).addTo(mapInstance as any);
        }
      });

      if (mapInstance?.addListener) {
        mapInstance.addListener('heading_changed', () =>
          setGeofenceStatus(status => ({ ...status }))
        );
      } else if (mapInstance?.on) {
        mapInstance.on('rotate', () => setGeofenceStatus(status => ({ ...status })));
      }
    },
    [boundaries, noGoZones]
  );
  // Layer visibility toggles
  const [showLayers, setShowLayers] = useState({
    boundaries: true,
    noGo: true,
    home: true,
    path: true
  });
  // Geofence status state
  const [geofenceStatus, setGeofenceStatus] = useState({
    insideBoundary: true,
    inNoGo: false,
    violation: false
  });
  // Drawing toolbar state
  const [drawingEnabled, setDrawingEnabled] = useState(false);
  const [drawingMode, setDrawingMode] = useState<'boundary' | 'no-go' | 'home' | null>(null);

  const handleBoundaryComplete = useCallback((coords: Array<{ lat: number; lng: number }>) => {
    // Append new boundary (auto-valid initial) - id placeholder
    const newBoundary = {
      id: `boundary-${Date.now()}`,
      name: `Boundary ${boundaries.length + 1}`,
      points: coords,
      isValid: true,
      vertices: coords.length
    } as any;
    setBoundaries(prev => [...prev, newBoundary]);
  }, [boundaries]);

  const handleNoGoComplete = useCallback((coords: Array<{ lat: number; lng: number }>) => {
    const newZone = {
      id: `nogo-${Date.now()}`,
      name: `No-Go ${noGoZones.length + 1}`,
      points: coords,
      isValid: true,
      vertices: coords.length,
      isEnabled: true
    } as any;
    setNoGoZones(prev => [...prev, newZone]);
  }, [noGoZones]);

  const handleHomeSet = useCallback((coord: { lat: number; lng: number }) => {
    const newHome = {
      id: `home-${Date.now()}`,
      name: `Home ${homeLocations.length + 1}`,
      type: 'charging_station',
      position: { latitude: coord.lat, longitude: coord.lng },
      is_default: homeLocations.length === 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    } as any;
    setHomeLocations(prev => [...prev, newHome]);
  }, [homeLocations]);

  // Determine if we should use full-width layout (desktop full-page mode); allow user toggle
  const [useFullWidth, setUseFullWidth] = useState(isDesktop);

  const robotPosition = status?.position ? {
    lat: status.position.lat,
    lng: status.position.lng,
    heading: status.position.heading
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
    // Initialize from build-time env, then override via runtime public config
    console.log('🗺️ Maps page initializing...');
    dispatch(initializeMapFromEnvironment());

    (async () => {
      try {
        const res = await fetch('/api/v1/public/config', { cache: 'no-store' });
        if (res.ok) {
          const data = await res.json();
          const gmaps = data?.google_maps || {};
          if (gmaps.api_key) {
            dispatch(setError(null));
            dispatch(updateConfig({ usageLevel: gmaps.usage_level || 'medium' } as any));
            dispatch(setPreferredProvider('google'));
            console.log('✅ Runtime Google Maps key found - selecting Google');
          } else {
            dispatch(setPreferredProvider('openstreetmap'));
            console.log('ℹ️ No runtime Google Maps key - using OpenStreetMap');
          }
        } else {
          console.warn('Public config fetch failed with status', res.status);
        }
      } catch (e) {
        console.warn('Failed to fetch public config; proceeding with env defaults', e);
      }
    })();

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

  // Point in polygon (ray casting) helper
  const pointInPolygon = useCallback((point: { lat: number; lng: number }, polygon: Array<{ lat: number; lng: number }>) => {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i].lat, yi = polygon[i].lng;
      const xj = polygon[j].lat, yj = polygon[j].lng;
      const intersect = ((yi > point.lng) !== (yj > point.lng)) &&
        (point.lat < (xj - xi) * (point.lng - yi) / (yj - yi + 1e-12) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }, []);

  // Compute geofence status whenever robot position or zones change
  useEffect(() => {
    if (!robotPosition) return;
    if (validBoundaries.length === 0) {
      // No boundaries defined => treat as inside, no violation
      setGeofenceStatus({ insideBoundary: true, inNoGo: false, violation: false });
      return;
    }
    const insideAny = validBoundaries.some(b => pointInPolygon(robotPosition, b.points));
    const inNoGo = activeNoGoZones.some(z => pointInPolygon(robotPosition, z.points));
    setGeofenceStatus({ insideBoundary: insideAny, inNoGo, violation: !insideAny || inNoGo });
    if ((!insideAny || inNoGo)) {
      console.warn('🚨 Geofence violation detected', { insideAny, inNoGo, position: robotPosition });
    }
  }, [robotPosition, validBoundaries, activeNoGoZones, pointInPolygon]);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        LawnBerry Maps
        {geofenceStatus.violation && (
          <Chip
            label={geofenceStatus.inNoGo ? 'IN NO-GO ZONE' : 'OUTSIDE BOUNDARY'}
            color="error"
            size="small"
            sx={{ ml: 2 }}
          />
        )}
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
            <>
            {/* Overview tab: full-width map with statistics stacked below */}
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
                    boundaries={showLayers.boundaries ? validBoundaries.map(b => ({ id: b.id, name: b.name, coordinates: b.points, type: 'boundary' as const })) : []}
                    noGoZones={showLayers.noGo ? activeNoGoZones.map(z => ({ id: z.id, name: z.name, coordinates: z.points, type: 'no-go' as const })) : []}
                    homeLocation={showLayers.home && defaultHomeLocation ? { lat: defaultHomeLocation.position.latitude, lng: defaultHomeLocation.position.longitude } : null}
                    enableDrawing={drawingEnabled}
                    drawingMode={drawingMode}
                    onBoundaryComplete={handleBoundaryComplete}
                    onNoGoZoneComplete={handleNoGoComplete}
                    onHomeLocationSet={handleHomeSet}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    onMapReady={handleMapReady}
                    geofenceViolation={geofenceStatus.violation}
                    geofenceInNoGo={geofenceStatus.inNoGo}
                    style={{ height: '100%' }}
                  >
                    {/* Overlays injected via MapContainer props */}
                    {drawingEnabled && (
                      <Box sx={{ position: 'absolute', top: 12, left: 12, zIndex: 1200, display: 'flex', gap: 1 }}>
                        <Chip
                          label="Boundary"
                          color={drawingMode === 'boundary' ? 'success' : 'default'}
                          onClick={() => setDrawingMode('boundary')}
                          variant={drawingMode === 'boundary' ? 'filled' : 'outlined'}
                          size="small"
                        />
                        <Chip
                          label="No-Go"
                          color={drawingMode === 'no-go' ? 'error' : 'default'}
                          onClick={() => setDrawingMode('no-go')}
                          variant={drawingMode === 'no-go' ? 'filled' : 'outlined'}
                          size="small"
                        />
                        <Chip
                          label="Home"
                          color={drawingMode === 'home' ? 'info' : 'default'}
                          onClick={() => setDrawingMode('home')}
                          variant={drawingMode === 'home' ? 'filled' : 'outlined'}
                          size="small"
                        />
                        <Chip
                          label="Finish"
                          color="primary"
                          onClick={() => { setDrawingEnabled(false); setDrawingMode(null); }}
                          variant="outlined"
                          size="small"
                        />
                      </Box>
                    )}
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
                      control={<Switch size="small" checked={showLayers.boundaries} onChange={e => setShowLayers(s => ({ ...s, boundaries: e.target.checked }))} />}
                      label="Boundaries"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" checked={showLayers.noGo} onChange={e => setShowLayers(s => ({ ...s, noGo: e.target.checked }))} />}
                      label="No-Go Zones"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" checked={showLayers.home} onChange={e => setShowLayers(s => ({ ...s, home: e.target.checked }))} />}
                      label="Home Locations"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" checked={showLayers.path} onChange={e => setShowLayers(s => ({ ...s, path: e.target.checked }))} />}
                      label="Robot Path"
                      sx={{ m: 0, fontSize: '0.875rem' }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" checked={drawingEnabled} onChange={e => { setDrawingEnabled(e.target.checked); if (!e.target.checked) setDrawingMode(null); }} />}
                      label="Draw"
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
                          {geofenceStatus.violation && (
                            <Chip
                              label={geofenceStatus.inNoGo ? 'No-Go Violation' : 'Boundary Violation'}
                              color="error"
                              size="small"
                              sx={{ ml: 1 }}
                            />
                          )}
                        </Typography>
                        {geofenceStatus.violation && (
                          <Alert severity="error" sx={{ mb: 2 }}>
                            {geofenceStatus.inNoGo ? 'Robot has entered a restricted no-go zone.' : 'Robot is outside all defined yard boundaries.'}
                          </Alert>
                        )}
                        
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
            </>
          )}

          {activeTab === 1 && (
            <>
            {/* Boundaries tab: stack the map on top and the editor below */}
            <Grid container spacing={3} direction="column">
              {/* Map row */}
              <Grid item xs={12}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    boundaries={validBoundaries.map(b => ({ id: b.id, name: b.name, coordinates: b.points, type: 'boundary' as const }))}
                    noGoZones={[]}
                    homeLocation={defaultHomeLocation ? { lat: defaultHomeLocation.position.latitude, lng: defaultHomeLocation.position.longitude } : null}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    onMapReady={handleMapReady}
                    geofenceViolation={geofenceStatus.violation}
                    geofenceInNoGo={geofenceStatus.inNoGo}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>

              {/* Editor row */}
              <Grid item xs={12}>
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
            </>
          )}

          {activeTab === 2 && (
            <>
            {/* No-Go Zones tab: stack the map on top and the editor below */}
            <Grid container spacing={3} direction="column">
              {/* Map row */}
              <Grid item xs={12}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    boundaries={validBoundaries.map(b => ({ id: b.id, name: b.name, coordinates: b.points, type: 'boundary' as const }))}
                    noGoZones={activeNoGoZones.map(z => ({ id: z.id, name: z.name, coordinates: z.points, type: 'no-go' as const }))}
                    homeLocation={defaultHomeLocation ? { lat: defaultHomeLocation.position.latitude, lng: defaultHomeLocation.position.longitude } : null}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    onMapReady={handleMapReady}
                    geofenceViolation={geofenceStatus.violation}
                    geofenceInNoGo={geofenceStatus.inNoGo}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>

              {/* Editor row */}
              <Grid item xs={12}>
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
            </>
          )}

          {activeTab === 3 && (
            <>
            {/* Home Locations tab: stack the map on top and the manager below */}
            <Grid container spacing={3} direction="column">
              {/* Map row */}
              <Grid item xs={12}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    boundaries={validBoundaries.map(b => ({ id: b.id, name: b.name, coordinates: b.points, type: 'boundary' as const }))}
                    noGoZones={activeNoGoZones.map(z => ({ id: z.id, name: z.name, coordinates: z.points, type: 'no-go' as const }))}
                    homeLocation={defaultHomeLocation ? { lat: defaultHomeLocation.position.latitude, lng: defaultHomeLocation.position.longitude } : null}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    onMapReady={handleMapReady}
                    geofenceViolation={geofenceStatus.violation}
                    geofenceInNoGo={geofenceStatus.inNoGo}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>

              {/* Manager row */}
              <Grid item xs={12}>
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
            </>
          )}

          {activeTab === 4 && (
            <>
            {/* Patterns tab: stack the map on top and the pattern visualizer below */}
            <Grid container spacing={3} direction="column">
              {/* Map row */}
              <Grid item xs={12}>
                <Paper sx={{ height: 600, overflow: 'hidden' }}>
                  <MapContainer
                    center={robotPosition || mapConfig.defaultCenter}
                    zoom={mapConfig.defaultZoom}
                    usageLevel={mapConfig.usageLevel}
                    preferredProvider={userPreferences.preferredProvider}
                    robotPosition={robotPosition}
                    boundaries={validBoundaries.map(b => ({ id: b.id, name: b.name, coordinates: b.points, type: 'boundary' as const }))}
                    noGoZones={activeNoGoZones.map(z => ({ id: z.id, name: z.name, coordinates: z.points, type: 'no-go' as const }))}
                    homeLocation={defaultHomeLocation ? { lat: defaultHomeLocation.position.latitude, lng: defaultHomeLocation.position.longitude } : null}
                    onProviderChange={(provider) => {
                      console.log('Provider changed to:', provider);
                    }}
                    onError={(error) => {
                      console.error('Map error:', error);
                    }}
                    onMapReady={handleMapReady}
                    geofenceViolation={geofenceStatus.violation}
                    geofenceInNoGo={geofenceStatus.inNoGo}
                    style={{ height: '100%' }}
                  />
                </Paper>
              </Grid>

              {/* Pattern visualizer row */}
              <Grid item xs={12}>
                <PatternVisualizer
                  mapInstance={mapRef.current}
                  mapProvider={userPreferences.preferredProvider}
                  boundaries={boundaries.map(b => b.points)}
                  noGoZones={noGoZones.map(zone => zone.points)}
                  homeLocations={homeLocations as any}
                  onPatternChange={handlePatternChange}
                  onPreviewStart={handlePreviewStart}
                />
              </Grid>
            </Grid>
            </>
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

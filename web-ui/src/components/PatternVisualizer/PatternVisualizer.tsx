import React, { useEffect, useState, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  Button,
  Switch,
  FormControlLabel,
  Grid,
  Alert,
  CircularProgress,
  Chip
} from '@mui/material';
import { Visibility, VisibilityOff, Refresh, PlayArrow } from '@mui/icons-material';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../../store/store';
import { MapProvider } from '../../types';

interface PatternPath {
  id: string;
  coordinates: Array<{ lat: number; lng: number }>;
  status: 'planned' | 'in-progress' | 'completed';
}

interface PatternVisualizationProps {
  mapInstance: google.maps.Map | L.Map | null;
  mapProvider: MapProvider;
  boundaries: Array<{ lat: number; lng: number }>;
  noGoZones?: Array<Array<{ lat: number; lng: number }>>;
  onPatternChange?: (pattern: string, parameters: any) => void;
  onPreviewStart?: (pattern: string) => void;
}

const PatternVisualizer: React.FC<PatternVisualizationProps> = ({
  mapInstance,
  mapProvider,
  boundaries,
  noGoZones = [],
  onPatternChange,
  onPreviewStart
}) => {
  const dispatch = useDispatch();
  const { patterns, currentPattern } = useSelector((state: RootState) => state.mower);
  
  const [selectedPattern, setSelectedPattern] = useState<string>(currentPattern || 'parallel');
  const [patternParameters, setPatternParameters] = useState<any>({});
  const [showPreview, setShowPreview] = useState(false);
  const [showCompleted, setShowCompleted] = useState(true);
  const [showPlanned, setShowPlanned] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [patternPaths, setPatternPaths] = useState<PatternPath[]>([]);
  const [overlays, setOverlays] = useState<any[]>([]);
  const [efficiency, setEfficiency] = useState<any>(null);

  // Initialize pattern parameters based on selected pattern
  useEffect(() => {
    const pattern = patterns.find(p => p.id === selectedPattern);
    if (pattern) {
      setPatternParameters(pattern.parameters);
    }
  }, [selectedPattern, patterns]);

  // Generate pattern paths when parameters change
  useEffect(() => {
    if (boundaries.length > 0 && showPreview) {
      generatePatternPaths();
    }
  }, [selectedPattern, patternParameters, boundaries, showPreview]);

  // Update map overlays when paths change
  useEffect(() => {
    if (mapInstance && patternPaths.length > 0) {
      updateMapOverlays();
    }
    return () => clearMapOverlays();
  }, [mapInstance, patternPaths, showPlanned, showCompleted, mapProvider]);

  const generatePatternPaths = useCallback(async () => {
    if (!boundaries.length || isGenerating) return;

    setIsGenerating(true);
    try {
      const response = await fetch(`/api/v1/patterns/${selectedPattern}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coordinates: boundaries,
          parameters: patternParameters
        })
      });

      if (!response.ok) {
        throw new Error('Failed to generate pattern');
      }

      const data = await response.json();
      
      // Convert paths to PatternPath format
      const newPaths: PatternPath[] = data.paths.map((path: any, index: number) => ({
        id: `path-${index}`,
        coordinates: path,
        status: 'planned' as const
      }));

      setPatternPaths(newPaths);

      // Get efficiency metrics
      const efficiencyResponse = await fetch(`/api/v1/patterns/${selectedPattern}/efficiency`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coordinates: boundaries,
          parameters: patternParameters
        })
      });

      if (efficiencyResponse.ok) {
        const efficiencyData = await efficiencyResponse.json();
        setEfficiency(efficiencyData);
      }

    } catch (error) {
      console.error('Failed to generate pattern:', error);
    } finally {
      setIsGenerating(false);
    }
  }, [boundaries, selectedPattern, patternParameters, isGenerating]);

  const updateMapOverlays = useCallback(() => {
    clearMapOverlays();
    
    if (!mapInstance || !patternPaths.length) return;

    const newOverlays: any[] = [];

    patternPaths.forEach((path) => {
      const shouldShow = (
        (path.status === 'planned' && showPlanned) ||
        (path.status === 'in-progress' && showPlanned) ||
        (path.status === 'completed' && showCompleted)
      );

      if (!shouldShow) return;

      const color = getPathColor(path.status);
      
      if (mapProvider === MapProvider.GOOGLE_MAPS && 'google' in window) {
        const polyline = new google.maps.Polyline({
          path: path.coordinates,
          geodesic: true,
          strokeColor: color,
          strokeOpacity: path.status === 'completed' ? 0.8 : 0.6,
          strokeWeight: path.status === 'in-progress' ? 4 : 2,
          map: mapInstance as google.maps.Map
        });
        newOverlays.push(polyline);
      } else if (mapProvider === MapProvider.OPENSTREETMAP && 'L' in window) {
        const leafletMap = mapInstance as L.Map;
        const polyline = L.polyline(
          path.coordinates.map(coord => [coord.lat, coord.lng]),
          {
            color: color,
            opacity: path.status === 'completed' ? 0.8 : 0.6,
            weight: path.status === 'in-progress' ? 4 : 2
          }
        ).addTo(leafletMap);
        newOverlays.push(polyline);
      }
    });

    setOverlays(newOverlays);
  }, [mapInstance, mapProvider, patternPaths, showPlanned, showCompleted]);

  const clearMapOverlays = useCallback(() => {
    overlays.forEach(overlay => {
      if (mapProvider === MapProvider.GOOGLE_MAPS) {
        overlay.setMap(null);
      } else if (mapProvider === MapProvider.OPENSTREETMAP) {
        overlay.remove();
      }
    });
    setOverlays([]);
  }, [overlays, mapProvider]);

  const getPathColor = (status: string): string => {
    switch (status) {
      case 'planned': return '#2196F3'; // Blue
      case 'in-progress': return '#FF9800'; // Orange
      case 'completed': return '#4CAF50'; // Green
      default: return '#9E9E9E'; // Grey
    }
  };

  const handleParameterChange = (param: string, value: any) => {
    const newParams = { ...patternParameters, [param]: value };
    setPatternParameters(newParams);
    onPatternChange?.(selectedPattern, newParams);
  };

  const handlePatternSelect = (pattern: string) => {
    setSelectedPattern(pattern);
    const patternConfig = patterns.find(p => p.id === pattern);
    if (patternConfig) {
      setPatternParameters(patternConfig.parameters);
      onPatternChange?.(pattern, patternConfig.parameters);
    }
  };

  const renderPatternControls = () => {
    const pattern = patterns.find(p => p.id === selectedPattern);
    if (!pattern) return null;

    return (
      <Grid container spacing={2}>
        {pattern.type === 'waves' && (
          <>
            <Grid item xs={6}>
              <Typography gutterBottom>Amplitude (m): {patternParameters.amplitude?.toFixed(2)}</Typography>
              <Slider
                value={patternParameters.amplitude || 0.75}
                onChange={(_, value) => handleParameterChange('amplitude', value)}
                min={0.25}
                max={2.0}
                step={0.05}
                valueLabelDisplay="auto"
              />
            </Grid>
            <Grid item xs={6}>
              <Typography gutterBottom>Wavelength (m): {patternParameters.wavelength?.toFixed(1)}</Typography>
              <Slider
                value={patternParameters.wavelength || 8.0}
                onChange={(_, value) => handleParameterChange('wavelength', value)}
                min={3.0}
                max={15.0}
                step={0.5}
                valueLabelDisplay="auto"
              />
            </Grid>
            <Grid item xs={6}>
              <Typography gutterBottom>Base Angle (°): {patternParameters.base_angle || 0}</Typography>
              <Slider
                value={patternParameters.base_angle || 0}
                onChange={(_, value) => handleParameterChange('base_angle', value)}
                min={0}
                max={180}
                step={5}
                valueLabelDisplay="auto"
              />
            </Grid>
          </>
        )}

        {pattern.type === 'crosshatch' && (
          <>
            <Grid item xs={6}>
              <Typography gutterBottom>First Angle (°): {patternParameters.first_angle || 45}</Typography>
              <Slider
                value={patternParameters.first_angle || 45}
                onChange={(_, value) => handleParameterChange('first_angle', value)}
                min={0}
                max={180}
                step={5}
                valueLabelDisplay="auto"
              />
            </Grid>
            <Grid item xs={6}>
              <Typography gutterBottom>Second Angle (°): {patternParameters.second_angle || 135}</Typography>
              <Slider
                value={patternParameters.second_angle || 135}
                onChange={(_, value) => handleParameterChange('second_angle', value)}
                min={0}
                max={180}
                step={5}
                valueLabelDisplay="auto"
              />
            </Grid>
          </>
        )}

        {(pattern.type === 'parallel' || pattern.type === 'checkerboard' || pattern.type === 'spiral') && (
          <>
            <Grid item xs={6}>
              <Typography gutterBottom>Spacing (m): {patternParameters.spacing?.toFixed(2)}</Typography>
              <Slider
                value={patternParameters.spacing || 0.3}
                onChange={(_, value) => handleParameterChange('spacing', value)}
                min={0.2}
                max={1.0}
                step={0.05}
                valueLabelDisplay="auto"
              />
            </Grid>
            {pattern.type === 'parallel' && (
              <Grid item xs={6}>
                <Typography gutterBottom>Angle (°): {patternParameters.angle || 0}</Typography>
                <Slider
                  value={patternParameters.angle || 0}
                  onChange={(_, value) => handleParameterChange('angle', value)}
                  min={0}
                  max={180}
                  step={5}
                  valueLabelDisplay="auto"
                />
              </Grid>
            )}
          </>
        )}

        <Grid item xs={6}>
          <Typography gutterBottom>Overlap: {((patternParameters.overlap || 0.1) * 100).toFixed(0)}%</Typography>
          <Slider
            value={patternParameters.overlap || 0.1}
            onChange={(_, value) => handleParameterChange('overlap', value)}
            min={0.0}
            max={0.5}
            step={0.01}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => `${(value * 100).toFixed(0)}%`}
          />
        </Grid>
      </Grid>
    );
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Pattern Visualization
        </Typography>

        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} md={6}>
            <FormControl fullWidth>
              <InputLabel>Mowing Pattern</InputLabel>
              <Select
                value={selectedPattern}
                onChange={(e) => handlePatternSelect(e.target.value)}
                label="Mowing Pattern"
              >
                {patterns.map((pattern) => (
                  <MenuItem key={pattern.id} value={pattern.id}>
                    {pattern.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} md={6}>
            <Box display="flex" gap={1} alignItems="center">
              <FormControlLabel
                control={
                  <Switch
                    checked={showPreview}
                    onChange={(e) => setShowPreview(e.target.checked)}
                  />
                }
                label="Show Preview"
              />
              
              <Button
                variant="outlined"
                size="small"
                onClick={generatePatternPaths}
                disabled={isGenerating || !boundaries.length}
                startIcon={isGenerating ? <CircularProgress size={16} /> : <Refresh />}
              >
                {isGenerating ? 'Generating...' : 'Refresh'}
              </Button>

              {onPreviewStart && (
                <Button
                  variant="contained"
                  size="small"
                  onClick={() => onPreviewStart(selectedPattern)}
                  startIcon={<PlayArrow />}
                  disabled={!patternPaths.length}
                >
                  Start Mowing
                </Button>
              )}
            </Box>
          </Grid>
        </Grid>

        {showPreview && (
          <>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Pattern Parameters
              </Typography>
              {renderPatternControls()}
            </Box>

            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Display Options
              </Typography>
              <Box display="flex" gap={2}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={showPlanned}
                      onChange={(e) => setShowPlanned(e.target.checked)}
                    />
                  }
                  label={
                    <Box display="flex" alignItems="center" gap={1}>
                      <Box width={12} height={12} bgcolor="#2196F3" />
                      Planned
                    </Box>
                  }
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={showCompleted}
                      onChange={(e) => setShowCompleted(e.target.checked)}
                    />
                  }
                  label={
                    <Box display="flex" alignItems="center" gap={1}>
                      <Box width={12} height={12} bgcolor="#4CAF50" />
                      Completed
                    </Box>
                  }
                />
              </Box>
            </Box>

            {efficiency && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Pattern Efficiency
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6} sm={3}>
                    <Chip
                      label={`${efficiency.total_distance}m total`}
                      size="small"
                      color="primary"
                    />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Chip
                      label={`${efficiency.coverage_area}m² area`}
                      size="small"
                      color="secondary"
                    />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Chip
                      label={`${efficiency.efficiency_score} efficiency`}
                      size="small"
                      color="success"
                    />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Chip
                      label={`${efficiency.estimated_time_minutes}min est.`}
                      size="small"
                      color="info"
                    />
                  </Grid>
                </Grid>
              </Box>
            )}

            {!boundaries.length && (
              <Alert severity="warning">
                Define yard boundaries first to preview mowing patterns.
              </Alert>
            )}

            {patternPaths.length > 0 && (
              <Alert severity="info">
                Showing {patternPaths.length} pattern paths on map. 
                Blue: Planned, Orange: In Progress, Green: Completed
              </Alert>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default PatternVisualizer;

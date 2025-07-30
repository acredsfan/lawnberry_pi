import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Card,
  CardContent,
  CardActions,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Grid,
  Paper,
  Divider
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Home as HomeIcon,
  Star as StarIcon,
  StarBorder as StarBorderIcon,
  GpsFixed as GpsIcon
} from '@mui/icons-material';
import L from 'leaflet';
import { 
  HomeLocation, 
  HomeLocationType, 
  CreateHomeLocationRequest,
  homeLocationService 
} from '../../services/homeLocationService';

interface Position {
  lat: number;
  lng: number;
}

interface LeafletHomeLocationManagerProps {
  map: L.Map | null;
  yardBoundaries?: Position[][];
  robotPosition?: Position;
  onHomeLocationsChange?: (locations: HomeLocation[]) => void;
}

const LeafletHomeLocationManager: React.FC<LeafletHomeLocationManagerProps> = ({
  map,
  yardBoundaries = [],
  robotPosition,
  onHomeLocationsChange
}) => {
  const [homeLocations, setHomeLocations] = useState<HomeLocation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingLocation, setEditingLocation] = useState<HomeLocation | null>(null);
  const [isPlacingMarker, setIsPlacingMarker] = useState(false);
  const [tempMarkerPosition, setTempMarkerPosition] = useState<Position | null>(null);
  const [markers, setMarkers] = useState<Map<string, L.Marker>>(new Map());
  const [tempMarker, setTempMarker] = useState<L.Marker | null>(null);

  // Form state
  const [formData, setFormData] = useState<CreateHomeLocationRequest>({
    name: '',
    type: HomeLocationType.CHARGING_STATION,
    position: { latitude: 0, longitude: 0 },
    description: ''
  });

  useEffect(() => {
    loadHomeLocations();
  }, []);

  useEffect(() => {
    if (map) {
      setupMapClickHandler();
      updateMarkersOnMap();
    }
    return () => {
      clearMapClickHandler();
    };
  }, [map, homeLocations, isPlacingMarker]);

  const loadHomeLocations = async () => {
    try {
      setIsLoading(true);
      const locations = await homeLocationService.getHomeLocations();
      setHomeLocations(locations);
      onHomeLocationsChange?.(locations);
    } catch (err) {
      setError('Failed to load home locations');
      console.error('Failed to load home locations:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const setupMapClickHandler = () => {
    if (!map || !isPlacingMarker) return;

    const handleMapClick = (event: L.LeafletMouseEvent) => {
      const position: Position = { lat: event.latlng.lat, lng: event.latlng.lng };
      setTempMarkerPosition(position);
      setFormData(prev => ({
        ...prev,
        position: { latitude: position.lat, longitude: position.lng }
      }));
    };

    map.on('click', handleMapClick);
  };

  const clearMapClickHandler = () => {
    if (!map) return;
    map.off('click');
  };

  const createHomeLocationIcon = (type: HomeLocationType, isDefault: boolean, isTemp: boolean = false) => {
    const color = isTemp ? '#ff9800' : isDefault ? '#f44336' : '#2196f3';
    const icon = homeLocationService.getHomeLocationIcon(type);
    
    return L.divIcon({
      html: `
        <div style="
          background: ${color};
          border: 2px solid white;
          border-radius: 50%;
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
          position: relative;
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        ">
          <span>${icon}</span>
          ${isDefault ? '<div style="position: absolute; top: -2px; right: -2px; background: #ffeb3b; border: 1px solid white; border-radius: 50%; width: 12px; height: 12px;"></div>' : ''}
        </div>
      `,
      className: 'home-location-marker',
      iconSize: [32, 32],
      iconAnchor: [16, 32]
    });
  };

  const updateMarkersOnMap = () => {
    if (!map) return;

    // Clear existing markers
    markers.forEach(marker => {
      map.removeLayer(marker);
    });
    if (tempMarker) {
      map.removeLayer(tempMarker);
      setTempMarker(null);
    }
    setMarkers(new Map());

    const newMarkers = new Map<string, L.Marker>();

    // Add markers for each home location
    homeLocations.forEach(location => {
      const position = L.latLng(location.position.latitude, location.position.longitude);
      const marker = L.marker(position, {
        icon: createHomeLocationIcon(location.type, location.is_default),
        draggable: true
      }).addTo(map);

      marker.bindPopup(`
        <div>
          <strong>${location.name}</strong><br/>
          ${homeLocationService.getHomeLocationTypeLabel(location.type, location.custom_type)}<br/>
          ${location.description || ''}
          ${location.is_default ? '<br/><em>Default Location</em>' : ''}
        </div>
      `);

      marker.on('dragend', () => {
        const newPos = marker.getLatLng();
        handleMarkerDragEnd(location.id, { lat: newPos.lat, lng: newPos.lng });
      });

      newMarkers.set(location.id, marker);
    });

    // Add temporary marker if placing
    if (tempMarkerPosition && isPlacingMarker) {
      const marker = L.marker(L.latLng(tempMarkerPosition.lat, tempMarkerPosition.lng), {
        icon: createHomeLocationIcon(formData.type, false, true)
      }).addTo(map);
      setTempMarker(marker);
    }

    setMarkers(newMarkers);
  };

  const handleMarkerDragEnd = async (locationId: string, newPosition: Position) => {
    try {
      // Validate boundary
      const validation = await homeLocationService.validateBoundary({
        latitude: newPosition.lat,
        longitude: newPosition.lng
      });

      if (!validation.is_within_boundary) {
        setError('Location must be within yard boundaries');
        loadHomeLocations(); // Reload to reset marker position
        return;
      }

      // Update location
      const location = homeLocations.find(l => l.id === locationId);
      if (location) {
        await homeLocationService.updateHomeLocation(locationId, {
          ...location,
          position: { latitude: newPosition.lat, longitude: newPosition.lng }
        });
        loadHomeLocations();
      }
    } catch (err) {
      setError('Failed to update location position');
      loadHomeLocations(); // Reload to reset marker position
    }
  };

  const handleAddLocation = () => {
    setEditingLocation(null);
    setFormData({
      name: '',
      type: HomeLocationType.CHARGING_STATION,
      position: { latitude: 0, longitude: 0 },
      description: ''
    });
    setTempMarkerPosition(null);
    setIsDialogOpen(true);
  };

  const handleEditLocation = (location: HomeLocation) => {
    setEditingLocation(location);
    setFormData({
      name: location.name,
      type: location.type,
      custom_type: location.custom_type,
      position: location.position,
      description: location.description || ''
    });
    setIsDialogOpen(true);
  };

  const handleDeleteLocation = async (locationId: string) => {
    if (!confirm('Are you sure you want to delete this home location?')) {
      return;
    }

    try {
      await homeLocationService.deleteHomeLocation(locationId);
      loadHomeLocations();
    } catch (err) {
      setError('Failed to delete home location');
    }
  };

  const handleSetDefault = async (locationId: string) => {
    try {
      await homeLocationService.setDefaultHomeLocation(locationId);
      loadHomeLocations();
    } catch (err) {
      setError('Failed to set default home location');
    }
  };

  const handleSubmit = async () => {
    try {
      setIsLoading(true);

      // Validate boundary
      const validation = await homeLocationService.validateBoundary(formData.position);
      if (!validation.is_within_boundary) {
        setError('Location must be within yard boundaries');
        return;
      }

      if (editingLocation) {
        await homeLocationService.updateHomeLocation(editingLocation.id, {
          ...editingLocation,
          ...formData
        });
      } else {
        await homeLocationService.createHomeLocation(formData);
      }

      loadHomeLocations();
      handleCloseDialog();
    } catch (err) {
      setError('Failed to save home location');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCloseDialog = () => {
    setIsDialogOpen(false);
    setEditingLocation(null);
    setIsPlacingMarker(false);
    setTempMarkerPosition(null);
    setError(null);
  };

  const handleStartPlacing = () => {
    setIsPlacingMarker(true);
    setTempMarkerPosition(null);
  };

  const handleManualCoordinates = () => {
    const lat = parseFloat(prompt('Enter latitude:') || '0');
    const lng = parseFloat(prompt('Enter longitude:') || '0');
    
    if (!isNaN(lat) && !isNaN(lng)) {
      setFormData(prev => ({
        ...prev,
        position: { latitude: lat, longitude: lng }
      }));
      setTempMarkerPosition({ lat, lng });
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6">Home Locations</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleAddLocation}
          disabled={isLoading}
        >
          Add Location
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Paper sx={{ maxHeight: 400, overflow: 'auto' }}>
        <List>
          {homeLocations.map((location) => (
            <React.Fragment key={location.id}>
              <ListItem>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <span>{homeLocationService.getHomeLocationIcon(location.type)}</span>
                      <span>{location.name}</span>
                      {location.is_default && (
                        <Chip size="small" label="Default" color="primary" />
                      )}
                    </Box>
                  }
                  secondary={
                    <Box>
                      <Typography variant="body2">
                        {homeLocationService.getHomeLocationTypeLabel(location.type, location.custom_type)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {location.position.latitude.toFixed(6)}, {location.position.longitude.toFixed(6)}
                      </Typography>
                      {location.description && (
                        <Typography variant="body2" color="text.secondary">
                          {location.description}
                        </Typography>
                      )}
                    </Box>
                  }
                />
                <ListItemSecondaryAction>
                  <IconButton
                    edge="end"
                    onClick={() => handleSetDefault(location.id)}
                    disabled={location.is_default}
                    title="Set as default"
                  >
                    {location.is_default ? <StarIcon color="primary" /> : <StarBorderIcon />}
                  </IconButton>
                  <IconButton
                    edge="end"
                    onClick={() => handleEditLocation(location)}
                    title="Edit location"
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    edge="end"
                    onClick={() => handleDeleteLocation(location.id)}
                    title="Delete location"
                  >
                    <DeleteIcon />
                  </IconButton>
                </ListItemSecondaryAction>
              </ListItem>
              <Divider />
            </React.Fragment>
          ))}
          {homeLocations.length === 0 && (
            <ListItem>
              <ListItemText
                primary="No home locations configured"
                secondary="Click 'Add Location' to create your first home location"
              />
            </ListItem>
          )}
        </List>
      </Paper>

      {/* Add/Edit Dialog */}
      <Dialog open={isDialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingLocation ? 'Edit Home Location' : 'Add Home Location'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Name"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                required
              />
            </Grid>
            
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Type</InputLabel>
                <Select
                  value={formData.type}
                  onChange={(e) => setFormData(prev => ({ 
                    ...prev, 
                    type: e.target.value as HomeLocationType,
                    custom_type: e.target.value === HomeLocationType.CUSTOM ? prev.custom_type : undefined
                  }))}
                >
                  {Object.values(HomeLocationType).map(type => (
                    <MenuItem key={type} value={type}>
                      {homeLocationService.getHomeLocationIcon(type)} {homeLocationService.getHomeLocationTypeLabel(type)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>

            {formData.type === HomeLocationType.CUSTOM && (
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Custom Type Name"
                  value={formData.custom_type || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, custom_type: e.target.value }))}
                  required
                />
              </Grid>
            )}

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={formData.description}
                onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                multiline
                rows={2}
              />
            </Grid>

            <Grid item xs={12}>
              <Typography variant="subtitle2" gutterBottom>
                Position
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                <Button
                  variant="outlined"
                  startIcon={<GpsIcon />}
                  onClick={handleStartPlacing}
                  disabled={isPlacingMarker}
                >
                  {isPlacingMarker ? 'Click on map...' : 'Place on Map'}
                </Button>
                <Button
                  variant="outlined"
                  onClick={handleManualCoordinates}
                >
                  Manual Entry
                </Button>
              </Box>
              
              <Grid container spacing={1}>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="Latitude"
                    type="number"
                    value={formData.position.latitude}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      position: { ...prev.position, latitude: parseFloat(e.target.value) || 0 }
                    }))}
                    inputProps={{ step: 0.000001 }}
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="Longitude"
                    type="number"
                    value={formData.position.longitude}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      position: { ...prev.position, longitude: parseFloat(e.target.value) || 0 }
                    }))}
                    inputProps={{ step: 0.000001 }}
                  />
                </Grid>
              </Grid>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={isLoading || !formData.name || !formData.position.latitude || !formData.position.longitude}
          >
            {isLoading ? 'Saving...' : editingLocation ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default LeafletHomeLocationManager;

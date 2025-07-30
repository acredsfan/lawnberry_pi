import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Chip,
  Alert,
  Snackbar,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  Cancel as CancelIcon,
  Warning as WarningIcon,
  Block as BlockIcon
} from '@mui/icons-material';
import { Loader } from '@googlemaps/js-api-loader';
import { NoGoZone, NoGoZonePoint, noGoZoneService } from '../../services/noGoZoneService';

interface BoundaryPoint {
  lat: number;
  lng: number;
}

interface NoGoZoneEditorProps {
  map: google.maps.Map | null;
  noGoZones: NoGoZone[];
  onNoGoZonesChange: (zones: NoGoZone[]) => void;
  yardBoundaries: BoundaryPoint[][];
  robotPosition?: BoundaryPoint;
}

const NoGoZoneEditor: React.FC<NoGoZoneEditorProps> = ({
  map,
  noGoZones,
  onNoGoZonesChange,
  yardBoundaries,
  robotPosition
}) => {
  const [drawingManager, setDrawingManager] = useState<google.maps.drawing.DrawingManager | null>(null);
  const [activePolygons, setActivePolygons] = useState<google.maps.Polygon[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [editingZone, setEditingZone] = useState<string | null>(null);
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [pendingPolygon, setPendingPolygon] = useState<google.maps.Polygon | null>(null);
  const [zoneName, setZoneName] = useState('');
  const [alert, setAlert] = useState<{ message: string; severity: 'error' | 'warning' | 'success' } | null>(null);
  const [clippedPoints, setClippedPoints] = useState<NoGoZonePoint[]>([]);

  // Initialize drawing manager
  useEffect(() => {
    if (!map || !window.google) return;

    const manager = new google.maps.drawing.DrawingManager({
      drawingMode: null,
      drawingControl: false,
      polygonOptions: {
        fillColor: '#f44336',
        fillOpacity: 0.3,
        strokeColor: '#d32f2f',
        strokeWeight: 2,
        strokePattern: [10, 5], // Dashed pattern for visual distinction
        editable: true,
        draggable: false
      }
    });

    manager.setMap(map);
    setDrawingManager(manager);

    // Handle polygon completion
    const handlePolygonComplete = async (polygon: google.maps.Polygon) => {
      const path = polygon.getPath();
      const points = path.getArray().map(latLng => ({
        lat: latLng.lat(),
        lng: latLng.lng()
      }));

      // Validate and clip to yard boundaries
      const validation = validateNoGoZone(points);
      
      if (!validation.isValid) {
        setAlert({ message: validation.error!, severity: 'error' });
        polygon.setMap(null);
        return;
      }

      // Clip to yard boundaries
      const clipped = await noGoZoneService.clipToYardBoundaries(points, yardBoundaries);
      
      if (clipped.length !== points.length) {
        setAlert({ 
          message: `Zone was automatically clipped to yard boundaries. ${points.length - clipped.length} points removed.`, 
          severity: 'warning' 
        });
        
        // Update polygon with clipped points
        const clippedPath = clipped.map(p => new google.maps.LatLng(p.lat, p.lng));
        polygon.setPath(clippedPath);
        setClippedPoints(clipped);
      }

      setPendingPolygon(polygon);
      setShowNameDialog(true);
      setIsDrawing(false);
      manager.setDrawingMode(null);
    };

    manager.addListener('polygoncomplete', handlePolygonComplete);

    return () => {
      manager.setMap(null);
    };
  }, [map, yardBoundaries]);

  // Render existing no-go zones
  useEffect(() => {
    if (!map || !window.google) return;

    // Clear existing polygons
    activePolygons.forEach(polygon => polygon.setMap(null));
    
    const newPolygons: google.maps.Polygon[] = [];

    noGoZones.forEach(zone => {
      if (zone.points.length < 3) return;

      const polygon = new google.maps.Polygon({
        paths: zone.points.map(p => ({ lat: p.lat, lng: p.lng })),
        fillColor: zone.isEnabled ? '#f44336' : '#9e9e9e',
        fillOpacity: zone.isEnabled ? 0.3 : 0.1,
        strokeColor: zone.isEnabled ? '#d32f2f' : '#757575',
        strokeWeight: 2,
        strokePattern: [10, 5],
        editable: editingZone === zone.id,
        draggable: false
      });

      polygon.setMap(map);
      newPolygons.push(polygon);

      // Add click listener for editing
      polygon.addListener('click', () => {
        if (!isDrawing && !editingZone) {
          handleEditZone(zone.id);
        }
      });

      // Add path change listener for editing
      if (editingZone === zone.id) {
        const path = polygon.getPath();
        path.addListener('set_at', () => handlePolygonEdit(zone.id, polygon));
        path.addListener('insert_at', () => handlePolygonEdit(zone.id, polygon));
      }
    });

    setActivePolygons(newPolygons);
  }, [map, noGoZones, editingZone, isDrawing]);

  const validateNoGoZone = (points: NoGoZonePoint[]): { isValid: boolean; error?: string } => {
    if (points.length < 3) {
      return { isValid: false, error: 'No-go zone must have at least 3 points' };
    }

    if (points.length > 100) {
      return { isValid: false, error: 'No-go zone cannot have more than 100 vertices' };
    }

    // Check if zone is within any yard boundary
    const isWithinBoundary = yardBoundaries.some(boundary => {
      return points.some(point => isPointInPolygon(point, boundary));
    });

    if (!isWithinBoundary && yardBoundaries.length > 0) {
      return { isValid: false, error: 'No-go zone must be within yard boundaries' };
    }

    return { isValid: true };
  };

  const isPointInPolygon = (point: NoGoZonePoint, polygon: BoundaryPoint[]): boolean => {
    let inside = false;
    const n = polygon.length;
    
    for (let i = 0, j = n - 1; i < n; j = i++) {
      if (((polygon[i].lat > point.lat) !== (polygon[j].lat > point.lat)) &&
          (point.lng < (polygon[j].lng - polygon[i].lng) * (point.lat - polygon[i].lat) / (polygon[j].lat - polygon[i].lat) + polygon[i].lng)) {
        inside = !inside;
      }
    }
    
    return inside;
  };

  const handleStartDrawing = () => {
    if (!drawingManager) return;
    
    setIsDrawing(true);
    drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON);
  };

  const handleCancelDrawing = () => {
    if (!drawingManager) return;
    
    setIsDrawing(false);
    drawingManager.setDrawingMode(null);
  };

  const handleSaveZone = async () => {
    if (!pendingPolygon || !zoneName.trim()) return;

    try {
      const path = pendingPolygon.getPath();
      const points = clippedPoints.length > 0 ? clippedPoints : path.getArray().map(latLng => ({
        lat: latLng.lat(),
        lng: latLng.lng()
      }));

      const newZone = await noGoZoneService.createNoGoZone({
        name: zoneName.trim(),
        points
      });

      onNoGoZonesChange([...noGoZones, newZone]);
      
      setShowNameDialog(false);
      setPendingPolygon(null);
      setZoneName('');
      setClippedPoints([]);
      setAlert({ message: 'No-go zone created successfully', severity: 'success' });
    } catch (error) {
      setAlert({ 
        message: error instanceof Error ? error.message : 'Failed to create no-go zone', 
        severity: 'error' 
      });
    }
  };

  const handleCancelSave = () => {
    if (pendingPolygon) {
      pendingPolygon.setMap(null);
    }
    setShowNameDialog(false);
    setPendingPolygon(null);
    setZoneName('');
    setClippedPoints([]);
  };

  const handleEditZone = (zoneId: string) => {
    setEditingZone(zoneId);
  };

  const handleSaveEdit = async () => {
    if (!editingZone) return;

    const editingPolygon = activePolygons.find(p => {
      // Find polygon by comparing with zone data
      const zone = noGoZones.find(z => z.id === editingZone);
      return zone && p.getPath().getLength() === zone.points.length;
    });

    if (!editingPolygon) return;

    try {
      const path = editingPolygon.getPath();
      const points = path.getArray().map(latLng => ({
        lat: latLng.lat(),
        lng: latLng.lng()
      }));

      // Clip to boundaries
      const clipped = await noGoZoneService.clipToYardBoundaries(points, yardBoundaries);
      
      if (clipped.length !== points.length) {
        setAlert({ 
          message: `Zone was clipped to yard boundaries. ${points.length - clipped.length} points removed.`, 
          severity: 'warning' 
        });
      }

      await noGoZoneService.updateNoGoZone(editingZone, { points: clipped });
      
      const updatedZones = noGoZones.map(zone =>
        zone.id === editingZone 
          ? { ...zone, points: clipped, vertices: clipped.length }
          : zone
      );
      
      onNoGoZonesChange(updatedZones);
      setEditingZone(null);
      setAlert({ message: 'No-go zone updated successfully', severity: 'success' });
    } catch (error) {
      setAlert({ 
        message: error instanceof Error ? error.message : 'Failed to update no-go zone', 
        severity: 'error' 
      });
    }
  };

  const handleCancelEdit = () => {
    setEditingZone(null);
  };

  const handlePolygonEdit = async (zoneId: string, polygon: google.maps.Polygon) => {
    // Real-time validation during editing
    const path = polygon.getPath();
    const points = path.getArray().map(latLng => ({
      lat: latLng.lat(),
      lng: latLng.lng()
    }));

    const validation = validateNoGoZone(points);
    
    // Update polygon style based on validation
    polygon.setOptions({
      strokeColor: validation.isValid ? '#d32f2f' : '#f44336',
      fillColor: validation.isValid ? '#f44336' : '#ffebee'
    });
  };

  const handleDeleteZone = async (zoneId: string) => {
    try {
      await noGoZoneService.deleteNoGoZone(zoneId);
      onNoGoZonesChange(noGoZones.filter(zone => zone.id !== zoneId));
      setAlert({ message: 'No-go zone deleted successfully', severity: 'success' });
    } catch (error) {
      setAlert({ 
        message: error instanceof Error ? error.message : 'Failed to delete no-go zone', 
        severity: 'error' 
      });
    }
  };

  const handleToggleZone = async (zoneId: string, enabled: boolean) => {
    try {
      await noGoZoneService.toggleNoGoZone(zoneId, enabled);
      const updatedZones = noGoZones.map(zone =>
        zone.id === zoneId ? { ...zone, isEnabled: enabled } : zone
      );
      onNoGoZonesChange(updatedZones);
      setAlert({ 
        message: `No-go zone ${enabled ? 'enabled' : 'disabled'} successfully`, 
        severity: 'success' 
      });
    } catch (error) {
      setAlert({ 
        message: error instanceof Error ? error.message : 'Failed to toggle no-go zone', 
        severity: 'error' 
      });
    }
  };

  return (
    <Box>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            No-Go Zone Management
          </Typography>
          
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Define areas within your yard that the mower should avoid. Zones are automatically clipped to yard boundaries.
          </Typography>

          <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {!isDrawing && !editingZone && (
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={handleStartDrawing}
                disabled={yardBoundaries.length === 0}
              >
                Add Zone
              </Button>
            )}
            
            {isDrawing && (
              <Button
                variant="outlined"
                startIcon={<CancelIcon />}
                onClick={handleCancelDrawing}
              >
                Cancel Drawing
              </Button>
            )}
            
            {editingZone && (
              <>
                <Button
                  variant="contained"
                  startIcon={<SaveIcon />}
                  onClick={handleSaveEdit}
                  color="primary"
                >
                  Save Changes
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<CancelIcon />}
                  onClick={handleCancelEdit}
                >
                  Cancel Edit
                </Button>
              </>
            )}
          </Box>

          {yardBoundaries.length === 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Please define yard boundaries first before creating no-go zones.
            </Alert>
          )}

          {isDrawing && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Click on the map to start drawing a no-go zone. Click the first point again to complete the zone.
            </Alert>
          )}

          {editingZone && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Drag the polygon vertices to modify the no-go zone shape.
            </Alert>
          )}

          <List>
            {noGoZones.map((zone) => (
              <ListItem key={zone.id} divider>
                <BlockIcon 
                  sx={{ 
                    mr: 2, 
                    color: zone.isEnabled ? 'error.main' : 'grey.400' 
                  }} 
                />
                <ListItemText
                  primary={zone.name}
                  secondary={
                    <Box>
                      <Typography variant="caption" display="block">
                        {zone.vertices} vertices • {zone.area ? `${Math.round(zone.area)} m²` : 'Area unknown'}
                      </Typography>
                      <Box sx={{ mt: 0.5 }}>
                        <Chip
                          label={zone.isEnabled ? 'Active' : 'Disabled'}
                          color={zone.isEnabled ? 'error' : 'default'}
                          size="small"
                          sx={{ mr: 1 }}
                        />
                        <Chip
                          label={zone.isValid ? 'Valid' : 'Invalid'}
                          color={zone.isValid ? 'success' : 'error'}
                          size="small"
                        />
                      </Box>
                    </Box>
                  }
                />
                <ListItemSecondaryAction>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={zone.isEnabled}
                        onChange={(e) => handleToggleZone(zone.id, e.target.checked)}
                        size="small"
                      />
                    }
                    label=""
                    sx={{ mr: 1 }}
                  />
                  <IconButton
                    edge="end"
                    onClick={() => handleEditZone(zone.id)}
                    disabled={isDrawing || (editingZone && editingZone !== zone.id)}
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    edge="end"
                    onClick={() => handleDeleteZone(zone.id)}
                    disabled={isDrawing || editingZone === zone.id}
                  >
                    <DeleteIcon />
                  </IconButton>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
          </List>

          {noGoZones.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
              No no-go zones defined. Click "Add Zone" to create your first zone.
            </Typography>
          )}
        </CardContent>
      </Card>

      {/* Zone naming dialog */}
      <Dialog open={showNameDialog} onClose={handleCancelSave}>
        <DialogTitle>Name Your No-Go Zone</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Zone Name"
            fullWidth
            variant="outlined"
            value={zoneName}
            onChange={(e) => setZoneName(e.target.value)}
            placeholder="e.g., Garden Beds, Pool Area"
          />
          {clippedPoints.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              Zone was automatically clipped to fit within yard boundaries.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelSave}>Cancel</Button>
          <Button 
            onClick={handleSaveZone} 
            variant="contained"
            disabled={!zoneName.trim()}
          >
            Save Zone
          </Button>
        </DialogActions>
      </Dialog>

      {/* Alert snackbar */}
      <Snackbar
        open={!!alert}
        autoHideDuration={6000}
        onClose={() => setAlert(null)}
      >
        <Alert severity={alert?.severity} onClose={() => setAlert(null)}>
          {alert?.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default NoGoZoneEditor;

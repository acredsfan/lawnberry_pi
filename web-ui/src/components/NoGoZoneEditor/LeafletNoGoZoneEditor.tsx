import React, { useEffect, useState, useCallback } from 'react';
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
  Block as BlockIcon
} from '@mui/icons-material';
import L from 'leaflet';
import 'leaflet-draw';
import { NoGoZone, NoGoZonePoint, noGoZoneService } from '../../services/noGoZoneService';

interface BoundaryPoint {
  lat: number;
  lng: number;
}

interface LeafletNoGoZoneEditorProps {
  map: L.Map | null;
  noGoZones: NoGoZone[];
  onNoGoZonesChange: (zones: NoGoZone[]) => void;
  yardBoundaries: BoundaryPoint[][];
  robotPosition?: BoundaryPoint;
}

const LeafletNoGoZoneEditor: React.FC<LeafletNoGoZoneEditorProps> = ({
  map,
  noGoZones,
  onNoGoZonesChange,
  yardBoundaries,
  robotPosition
}) => {
  const [drawControl, setDrawControl] = useState<L.Control.Draw | null>(null);
  const [drawnItems, setDrawnItems] = useState<L.FeatureGroup | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [editingZone, setEditingZone] = useState<string | null>(null);
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [pendingLayer, setPendingLayer] = useState<L.Polygon | null>(null);
  const [zoneName, setZoneName] = useState('');
  const [alert, setAlert] = useState<{ message: string; severity: 'error' | 'warning' | 'success' } | null>(null);
  const [clippedPoints, setClippedPoints] = useState<NoGoZonePoint[]>([]);

  // Initialize Leaflet Draw
  useEffect(() => {
    if (!map) return;

    const drawnItemsLayer = new L.FeatureGroup();
    map.addLayer(drawnItemsLayer);
    setDrawnItems(drawnItemsLayer);

    const drawControl = new L.Control.Draw({
      position: 'topright',
      draw: {
        polygon: {
          allowIntersection: false,
          drawError: {
            color: '#e1e100',
            message: '<strong>Error:</strong> shape edges cannot cross!'
          },
          shapeOptions: {
            color: '#d32f2f',
            fillColor: '#f44336',
            fillOpacity: 0.3,
            weight: 2,
            dashArray: '10, 5'
          }
        },
        polyline: false,
        rectangle: false,
        circle: false,
        marker: false,
        circlemarker: false
      },
      edit: {
        featureGroup: drawnItemsLayer,
        remove: false
      }
    });

    // Don't add to map by default - we'll control it manually
    setDrawControl(drawControl);

    // Handle draw events
    const handleDrawCreated = async (e: any) => {
      const layer = e.layer as L.Polygon;
      const latlngs = layer.getLatLngs()[0] as L.LatLng[];
      const points = latlngs.map(ll => ({ lat: ll.lat, lng: ll.lng }));

      // Validate and clip to yard boundaries
      const validation = validateNoGoZone(points);
      
      if (!validation.isValid) {
        setAlert({ message: validation.error!, severity: 'error' });
        return;
      }

      // Clip to yard boundaries
      const clipped = await noGoZoneService.clipToYardBoundaries(points, yardBoundaries);
      
      if (clipped.length !== points.length) {
        setAlert({ 
          message: `Zone was automatically clipped to yard boundaries. ${points.length - clipped.length} points removed.`, 
          severity: 'warning' 
        });
        
        // Update layer with clipped points
        const clippedLatLngs = clipped.map(p => L.latLng(p.lat, p.lng));
        layer.setLatLngs([clippedLatLngs]);
        setClippedPoints(clipped);
      }

      setPendingLayer(layer);
      setShowNameDialog(true);
      setIsDrawing(false);
    };

    const handleDrawStart = () => {
      setIsDrawing(true);
    };

    const handleDrawStop = () => {
      setIsDrawing(false);
    };

    map.on(L.Draw.Event.CREATED, handleDrawCreated);
    map.on(L.Draw.Event.DRAWSTART, handleDrawStart);
    map.on(L.Draw.Event.DRAWSTOP, handleDrawStop);

    return () => {
      map.off(L.Draw.Event.CREATED, handleDrawCreated);
      map.off(L.Draw.Event.DRAWSTART, handleDrawStart);
      map.off(L.Draw.Event.DRAWSTOP, handleDrawStop);
      
      if (drawControl && map.hasLayer(drawControl as any)) {
        map.removeControl(drawControl);
      }
      if (drawnItemsLayer) {
        map.removeLayer(drawnItemsLayer);
      }
    };
  }, [map, yardBoundaries]);

  // Render existing no-go zones
  useEffect(() => {
    if (!map || !drawnItems) return;

    // Clear existing layers
    drawnItems.clearLayers();

    noGoZones.forEach(zone => {
      if (zone.points.length < 3) return;

      const latlngs = zone.points.map(p => L.latLng(p.lat, p.lng));
      const polygon = L.polygon([latlngs], {
        color: zone.isEnabled ? '#d32f2f' : '#757575',
        fillColor: zone.isEnabled ? '#f44336' : '#9e9e9e',
        fillOpacity: zone.isEnabled ? 0.3 : 0.1,
        weight: 2,
        dashArray: '10, 5'
      });

      // Add zone info to layer
      (polygon as any)._zoneInfo = {
        id: zone.id,
        name: zone.name,
        isEnabled: zone.isEnabled
      };

      polygon.addTo(drawnItems);

      // Add click handler for editing
      polygon.on('click', () => {
        if (!isDrawing && !editingZone) {
          handleEditZone(zone.id);
        }
      });

      // Add popup with zone info
      polygon.bindPopup(`
        <div>
          <strong>${zone.name}</strong><br/>
          ${zone.vertices} vertices • ${zone.area ? Math.round(zone.area) + ' m²' : 'Area unknown'}<br/>
          Status: ${zone.isEnabled ? 'Active' : 'Disabled'}
        </div>
      `);
    });
  }, [map, drawnItems, noGoZones, editingZone, isDrawing]);

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
    if (!drawControl || !map) return;
    
    if (!map.hasLayer(drawControl as any)) {
      map.addControl(drawControl);
    }
    
    // Enable polygon drawing
    (drawControl as any)._toolbars.draw._modes.polygon.handler.enable();
  };

  const handleCancelDrawing = () => {
    if (!drawControl || !map) return;
    
    // Disable drawing
    (drawControl as any)._toolbars.draw._modes.polygon.handler.disable();
    setIsDrawing(false);
  };

  const handleSaveZone = async () => {
    if (!pendingLayer || !zoneName.trim()) return;

    try {
      const latlngs = pendingLayer.getLatLngs()[0] as L.LatLng[];
      const points = clippedPoints.length > 0 ? clippedPoints : latlngs.map(ll => ({
        lat: ll.lat,
        lng: ll.lng
      }));

      const newZone = await noGoZoneService.createNoGoZone({
        name: zoneName.trim(),
        points
      });

      onNoGoZonesChange([...noGoZones, newZone]);
      
      setShowNameDialog(false);
      setPendingLayer(null);
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
    if (pendingLayer && drawnItems) {
      drawnItems.removeLayer(pendingLayer);
    }
    setShowNameDialog(false);
    setPendingLayer(null);
    setZoneName('');
    setClippedPoints([]);
  };

  const handleEditZone = (zoneId: string) => {
    setEditingZone(zoneId);
    
    if (drawControl && map) {
      if (!map.hasLayer(drawControl as any)) {
        map.addControl(drawControl);
      }
      // Enable edit mode
      (drawControl as any)._toolbars.edit._modes.edit.handler.enable();
    }
  };

  const handleSaveEdit = async () => {
    if (!editingZone || !drawnItems) return;

    try {
      // Find the layer being edited
      let editedLayer: L.Polygon | null = null;
      drawnItems.eachLayer((layer) => {
        const zoneInfo = (layer as any)._zoneInfo;
        if (zoneInfo && zoneInfo.id === editingZone) {
          editedLayer = layer as L.Polygon;
        }
      });

      if (!editedLayer) return;

      const latlngs = editedLayer.getLatLngs()[0] as L.LatLng[];
      const points = latlngs.map(ll => ({ lat: ll.lat, lng: ll.lng }));

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
      
      // Disable edit mode
      if (drawControl) {
        (drawControl as any)._toolbars.edit._modes.edit.handler.disable();
      }
      
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
    
    // Disable edit mode
    if (drawControl) {
      (drawControl as any)._toolbars.edit._modes.edit.handler.disable();
    }
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
              Use the edit tools to modify the no-go zone shape. Drag vertices or click to add new ones.
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

export default LeafletNoGoZoneEditor;

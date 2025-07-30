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
  Snackbar
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  Cancel as CancelIcon,
  Warning as WarningIcon
} from '@mui/icons-material';
import * as L from 'leaflet';
import 'leaflet-draw';

interface BoundaryPoint {
  lat: number;
  lng: number;
}

interface Boundary {
  id: string;
  name: string;
  points: BoundaryPoint[];
  area?: number;
  isValid: boolean;
  vertices: number;
}

interface LeafletBoundaryEditorProps {
  map: L.Map | null;
  boundaries: Boundary[];
  onBoundariesChange: (boundaries: Boundary[]) => void;
  robotPosition?: BoundaryPoint;
}

const LeafletBoundaryEditor: React.FC<LeafletBoundaryEditorProps> = ({
  map,
  boundaries,
  onBoundariesChange,
  robotPosition
}) => {
  const [drawControl, setDrawControl] = useState<L.Control.Draw | null>(null);
  const [featureGroup, setFeatureGroup] = useState<L.FeatureGroup | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [editingBoundary, setEditingBoundary] = useState<string | null>(null);
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [pendingLayer, setPendingLayer] = useState<L.Polygon | null>(null);
  const [boundaryName, setBoundaryName] = useState('');
  const [alert, setAlert] = useState<{ message: string; severity: 'error' | 'warning' | 'success' } | null>(null);
  const [boundaryLayers, setBoundaryLayers] = useState<Map<string, L.Polygon>>(new Map());

  // Initialize drawing controls
  useEffect(() => {
    if (!map) return;

    const editableLayers = new L.FeatureGroup();
    map.addLayer(editableLayers);
    setFeatureGroup(editableLayers);

    const drawControl = new L.Control.Draw({
      position: 'topright',
      draw: {
        polyline: false,
        circle: false,
        rectangle: false,
        marker: false,
        circlemarker: false,
        polygon: {
          allowIntersection: false,
          drawError: {
            color: '#e1e100',
            message: '<strong>Error:</strong> Shape edges cannot cross!'
          },
          shapeOptions: {
            color: '#4CAF50',
            fillOpacity: 0.2,
            weight: 2
          }
        }
      },
      edit: {
        featureGroup: editableLayers,
        remove: false
      }
    });

    setDrawControl(drawControl);

    // Handle drawing events
    const handleDrawCreated = (e: any) => {
      const layer = e.layer as L.Polygon;
      const latlngs = layer.getLatLngs()[0] as L.LatLng[];
      const points = latlngs.map(latlng => ({
        lat: latlng.lat,
        lng: latlng.lng
      }));

      // Validate polygon
      const validation = validatePolygon(points);
      
      if (!validation.isValid) {
        setAlert({ message: validation.error!, severity: 'error' });
        return;
      }

      setPendingLayer(layer);
      setBoundaryName(`Boundary ${boundaries.length + 1}`);
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
      if (drawControl && map) {
        map.removeControl(drawControl);
      }
      if (editableLayers && map) {
        map.removeLayer(editableLayers);
      }
      map.off(L.Draw.Event.CREATED, handleDrawCreated);
      map.off(L.Draw.Event.DRAWSTART, handleDrawStart);
      map.off(L.Draw.Event.DRAWSTOP, handleDrawStop);
    };
  }, [map, boundaries]);

  // Render existing boundaries on map
  useEffect(() => {
    if (!map || !featureGroup) return;

    // Clear existing layers
    boundaryLayers.forEach(layer => {
      if (featureGroup.hasLayer(layer)) {
        featureGroup.removeLayer(layer);
      }
    });

    const newBoundaryLayers = new Map<string, L.Polygon>();

    boundaries.forEach(boundary => {
      const latlngs = boundary.points.map(point => [point.lat, point.lng] as [number, number]);
      
      const polygon = L.polygon(latlngs, {
        color: boundary.isValid ? '#4CAF50' : '#F44336',
        weight: 2,
        fillOpacity: 0.2,
        fillColor: boundary.isValid ? '#4CAF50' : '#F44336'
      });

      polygon.addTo(featureGroup);
      newBoundaryLayers.set(boundary.id, polygon);

      // Add popup with boundary info
      polygon.bindPopup(`
        <strong>${boundary.name}</strong><br/>
        Vertices: ${boundary.vertices}<br/>
        Area: ${formatArea(boundary.area)}<br/>
        Status: ${boundary.isValid ? 'Valid' : 'Invalid'}
      `);
    });

    setBoundaryLayers(newBoundaryLayers);

    return () => {
      newBoundaryLayers.forEach(layer => {
        if (featureGroup.hasLayer(layer)) {
          featureGroup.removeLayer(layer);
        }
      });
    };
  }, [map, featureGroup, boundaries]);

  const validatePolygon = (points: BoundaryPoint[]) => {
    // Check minimum points
    if (points.length < 3) {
      return { isValid: false, error: 'Boundary must have at least 3 points' };
    }

    // Check maximum vertices
    if (points.length > 100) {
      return { isValid: false, error: 'Boundary cannot have more than 100 vertices' };
    }

    // Calculate area using shoelace formula
    let area = 0;
    for (let i = 0; i < points.length; i++) {
      const j = (i + 1) % points.length;
      area += points[i].lat * points[j].lng;
      area -= points[j].lat * points[i].lng;
    }
    area = Math.abs(area) / 2;

    // Convert to square meters (rough approximation)
    const areaM2 = area * 111320 * 111320 * Math.cos(points[0].lat * Math.PI / 180);

    // Check minimum area (10 square meters)
    if (areaM2 < 10) {
      return { isValid: false, error: 'Boundary area must be at least 10 square meters' };
    }

    // Check for self-intersection (simple check)
    if (hasSelfIntersection(points)) {
      return { isValid: false, error: 'Boundary cannot intersect itself' };
    }

    return { isValid: true, area: areaM2 };
  };

  const hasSelfIntersection = (points: BoundaryPoint[]): boolean => {
    // Simple self-intersection check using line segment intersection
    for (let i = 0; i < points.length; i++) {
      const line1 = {
        start: points[i],
        end: points[(i + 1) % points.length]
      };

      for (let j = i + 2; j < points.length; j++) {
        if (j === points.length - 1 && i === 0) continue; // Skip adjacent segments
        
        const line2 = {
          start: points[j],
          end: points[(j + 1) % points.length]
        };

        if (lineSegmentsIntersect(line1.start, line1.end, line2.start, line2.end)) {
          return true;
        }
      }
    }
    return false;
  };

  const lineSegmentsIntersect = (p1: BoundaryPoint, q1: BoundaryPoint, p2: BoundaryPoint, q2: BoundaryPoint): boolean => {
    const orientation = (p: BoundaryPoint, q: BoundaryPoint, r: BoundaryPoint) => {
      const val = (q.lng - p.lng) * (r.lat - q.lat) - (q.lat - p.lat) * (r.lng - q.lng);
      if (Math.abs(val) < 1e-10) return 0; // Collinear
      return val > 0 ? 1 : 2; // Clockwise or counterclockwise
    };

    const o1 = orientation(p1, q1, p2);
    const o2 = orientation(p1, q1, q2);
    const o3 = orientation(p2, q2, p1);
    const o4 = orientation(p2, q2, q1);

    return (o1 !== o2 && o3 !== o4);
  };

  const startDrawing = () => {
    if (drawControl && map) {
      map.addControl(drawControl);
      setIsDrawing(true);
    }
  };

  const stopDrawing = () => {
    if (drawControl && map) {
      map.removeControl(drawControl);
      setIsDrawing(false);
    }
  };

  const handleSaveBoundary = () => {
    if (pendingLayer && boundaryName.trim() && featureGroup) {
      const latlngs = pendingLayer.getLatLngs()[0] as L.LatLng[];
      const points = latlngs.map(latlng => ({
        lat: latlng.lat,
        lng: latlng.lng
      }));

      const validation = validatePolygon(points);
      
      const newBoundary: Boundary = {
        id: `boundary-${Date.now()}`,
        name: boundaryName.trim(),
        points,
        area: validation.area,
        isValid: validation.isValid,
        vertices: points.length
      };

      const updatedBoundaries = [...boundaries, newBoundary];
      onBoundariesChange(updatedBoundaries);
      
      // Add the layer to the feature group
      featureGroup.addLayer(pendingLayer);
      
      setShowNameDialog(false);
      setBoundaryName('');
      setPendingLayer(null);
      stopDrawing();
      
      setAlert({ message: 'Boundary saved successfully', severity: 'success' });
    }
  };

  const handleCancelBoundary = () => {
    if (pendingLayer) {
      // Layer will be automatically removed since it wasn't added to feature group
      setPendingLayer(null);
    }
    setShowNameDialog(false);
    setBoundaryName('');
    stopDrawing();
  };

  const handleEditBoundary = (boundaryId: string) => {
    // For Leaflet, editing is handled through the draw control's edit mode
    // This would require more complex implementation with edit events
    setAlert({ message: 'Edit mode not yet implemented for OpenStreetMap', severity: 'warning' });
  };

  const handleDeleteBoundary = (boundaryId: string) => {
    const layer = boundaryLayers.get(boundaryId);
    if (layer && featureGroup) {
      featureGroup.removeLayer(layer);
    }
    
    const updatedBoundaries = boundaries.filter(b => b.id !== boundaryId);
    onBoundariesChange(updatedBoundaries);
    setAlert({ message: 'Boundary deleted', severity: 'success' });
  };

  const formatArea = (area?: number) => {
    if (!area) return 'Unknown';
    if (area < 1000) return `${Math.round(area)} m²`;
    return `${(area / 10000).toFixed(2)} ha`;
  };

  return (
    <Box>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Yard Boundaries (OpenStreetMap)
          </Typography>
          
          <Box sx={{ mb: 2 }}>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={startDrawing}
              disabled={isDrawing}
              sx={{ mr: 1 }}
            >
              {isDrawing ? 'Drawing...' : 'Draw Boundary'}
            </Button>
            
            {isDrawing && (
              <Button
                variant="outlined"
                startIcon={<CancelIcon />}
                onClick={stopDrawing}
              >
                Cancel
              </Button>
            )}
          </Box>

          <List>
            {boundaries.map((boundary) => (
              <ListItem key={boundary.id} divider>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {boundary.name}
                      {!boundary.isValid && (
                        <Chip
                          icon={<WarningIcon />}
                          label="Invalid"
                          color="error"
                          size="small"
                        />
                      )}
                    </Box>
                  }
                  secondary={
                    <Typography variant="body2" color="text.secondary">
                      {boundary.vertices} vertices • {formatArea(boundary.area)}
                    </Typography>
                  }
                />
                <ListItemSecondaryAction>
                  <IconButton
                    edge="end"
                    onClick={() => handleEditBoundary(boundary.id)}
                    color="default"
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    edge="end"
                    onClick={() => handleDeleteBoundary(boundary.id)}
                    color="error"
                  >
                    <DeleteIcon />
                  </IconButton>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
            
            {boundaries.length === 0 && (
              <ListItem>
                <ListItemText
                  primary="No boundaries defined"
                  secondary="Click 'Draw Boundary' to start defining your yard boundaries"
                />
              </ListItem>
            )}
          </List>
        </CardContent>
      </Card>

      {/* Boundary name dialog */}
      <Dialog open={showNameDialog} onClose={handleCancelBoundary}>
        <DialogTitle>Name Your Boundary</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Boundary Name"
            fullWidth
            variant="outlined"
            value={boundaryName}
            onChange={(e) => setBoundaryName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelBoundary}>Cancel</Button>
          <Button 
            onClick={handleSaveBoundary}
            variant="contained"
            disabled={!boundaryName.trim()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Alert snackbar */}
      <Snackbar
        open={!!alert}
        autoHideDuration={6000}
        onClose={() => setAlert(null)}
      >
        {alert && (
          <Alert
            onClose={() => setAlert(null)}
            severity={alert.severity}
            sx={{ width: '100%' }}
          >
            {alert.message}
          </Alert>
        )}
      </Snackbar>
    </Box>
  );
};

export default LeafletBoundaryEditor;

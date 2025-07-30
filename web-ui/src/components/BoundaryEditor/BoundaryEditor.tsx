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
import { Loader } from '@googlemaps/js-api-loader';

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

interface BoundaryEditorProps {
  map: google.maps.Map | null;
  boundaries: Boundary[];
  onBoundariesChange: (boundaries: Boundary[]) => void;
  robotPosition?: BoundaryPoint;
}

const BoundaryEditor: React.FC<BoundaryEditorProps> = ({
  map,
  boundaries,
  onBoundariesChange,
  robotPosition
}) => {
  const [drawingManager, setDrawingManager] = useState<google.maps.drawing.DrawingManager | null>(null);
  const [activePolygons, setActivePolygons] = useState<google.maps.Polygon[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [editingBoundary, setEditingBoundary] = useState<string | null>(null);
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [pendingPolygon, setPendingPolygon] = useState<google.maps.Polygon | null>(null);
  const [boundaryName, setBoundaryName] = useState('');
  const [alert, setAlert] = useState<{ message: string; severity: 'error' | 'warning' | 'success' } | null>(null);

  // Initialize drawing manager
  useEffect(() => {
    if (!map || !window.google) return;

    const manager = new google.maps.drawing.DrawingManager({
      drawingMode: null,
      drawingControl: false,
      polygonOptions: {
        fillColor: '#4CAF50',
        fillOpacity: 0.2,
        strokeColor: '#4CAF50',
        strokeWeight: 2,
        editable: true,
        draggable: false
      }
    });

    manager.setMap(map);
    setDrawingManager(manager);

    // Handle polygon completion
    const handlePolygonComplete = (polygon: google.maps.Polygon) => {
      const path = polygon.getPath();
      const points = path.getArray().map(latLng => ({
        lat: latLng.lat(),
        lng: latLng.lng()
      }));

      // Validate polygon
      const validation = validatePolygon(points);
      
      if (!validation.isValid) {
        setAlert({ message: validation.error!, severity: 'error' });
        polygon.setMap(null);
        return;
      }

      // Auto-merge overlapping polygons
      const mergedPolygons = mergeOverlappingPolygons([...boundaries, {
        id: `boundary-${Date.now()}`,
        name: `Boundary ${boundaries.length + 1}`,
        points,
        isValid: true,
        vertices: points.length
      }]);

      if (mergedPolygons.length < boundaries.length + 1) {
        setAlert({ message: 'Overlapping boundaries automatically merged', severity: 'success' });
      }

      setPendingPolygon(polygon);
      setBoundaryName(`Boundary ${boundaries.length + 1}`);
      setShowNameDialog(true);
    };

    manager.addListener('polygoncomplete', handlePolygonComplete);

    return () => {
      if (manager) {
        google.maps.event.clearInstanceListeners(manager);
        manager.setMap(null);
      }
    };
  }, [map, boundaries]);

  // Render existing boundaries on map
  useEffect(() => {
    if (!map) return;

    // Clear existing polygons
    activePolygons.forEach(polygon => polygon.setMap(null));
    
    const newPolygons: google.maps.Polygon[] = [];

    boundaries.forEach(boundary => {
      const polygon = new google.maps.Polygon({
        paths: boundary.points,
        fillColor: boundary.isValid ? '#4CAF50' : '#F44336',
        fillOpacity: 0.2,
        strokeColor: boundary.isValid ? '#4CAF50' : '#F44336',
        strokeWeight: 2,
        editable: editingBoundary === boundary.id,
        map: map
      });

      // Add edit listeners
      if (editingBoundary === boundary.id) {
        const updateBoundary = () => {
          const path = polygon.getPath();
          const updatedPoints = path.getArray().map(latLng => ({
            lat: latLng.lat(),
            lng: latLng.lng()
          }));

          const validation = validatePolygon(updatedPoints);
          const updatedBoundaries = boundaries.map(b => 
            b.id === boundary.id 
              ? { ...b, points: updatedPoints, isValid: validation.isValid, vertices: updatedPoints.length }
              : b
          );

          onBoundariesChange(updatedBoundaries);
        };

        polygon.getPath().addListener('set_at', updateBoundary);
        polygon.getPath().addListener('insert_at', updateBoundary);
        polygon.getPath().addListener('remove_at', updateBoundary);
      }

      newPolygons.push(polygon);
    });

    setActivePolygons(newPolygons);

    return () => {
      newPolygons.forEach(polygon => polygon.setMap(null));
    };
  }, [map, boundaries, editingBoundary, onBoundariesChange]);

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

  const mergeOverlappingPolygons = (polygons: Boundary[]): Boundary[] => {
    // Simple merge logic - in a real implementation, use a proper geometry library
    // For now, just return the input polygons
    // TODO: Implement proper polygon union using turf.js or similar
    return polygons;
  };

  const startDrawing = () => {
    if (drawingManager) {
      drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON);
      setIsDrawing(true);
    }
  };

  const stopDrawing = () => {
    if (drawingManager) {
      drawingManager.setDrawingMode(null);
      setIsDrawing(false);
    }
  };

  const handleSaveBoundary = () => {
    if (pendingPolygon && boundaryName.trim()) {
      const path = pendingPolygon.getPath();
      const points = path.getArray().map(latLng => ({
        lat: latLng.lat(),
        lng: latLng.lng()
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
      
      setShowNameDialog(false);
      setBoundaryName('');
      setPendingPolygon(null);
      stopDrawing();
      
      setAlert({ message: 'Boundary saved successfully', severity: 'success' });
    }
  };

  const handleCancelBoundary = () => {
    if (pendingPolygon) {
      pendingPolygon.setMap(null);
      setPendingPolygon(null);
    }
    setShowNameDialog(false);
    setBoundaryName('');
    stopDrawing();
  };

  const handleEditBoundary = (boundaryId: string) => {
    setEditingBoundary(editingBoundary === boundaryId ? null : boundaryId);
  };

  const handleDeleteBoundary = (boundaryId: string) => {
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
            Yard Boundaries
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
                    color={editingBoundary === boundary.id ? 'primary' : 'default'}
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

export default BoundaryEditor;

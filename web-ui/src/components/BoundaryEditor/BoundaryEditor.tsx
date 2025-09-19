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
// Geometry operations
import { union, polygon as turfPolygon, Feature, Polygon, booleanIntersects } from '@turf/turf';

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
  const [activePolygons, setActivePolygons] = useState<google.maps.Polygon[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [editingBoundary, setEditingBoundary] = useState<string | null>(null);
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [pendingPolygon, setPendingPolygon] = useState<google.maps.Polygon | null>(null);
  const [boundaryName, setBoundaryName] = useState('');
  const [alert, setAlert] = useState<{ message: string; severity: 'error' | 'warning' | 'success' } | null>(null);
  const drawingListenersRef = useRef<google.maps.MapsEventListener[]>([]);
  const drawingSessionRef = useRef<{ polygon: google.maps.Polygon | null; points: BoundaryPoint[] }>({
    polygon: null,
    points: []
  });
  const drawingMapOptionsRef = useRef<{ disableDoubleClickZoom: boolean | null } | null>(null);

  // Custom polygon completion handler (replaces deprecated drawing library)
  const handlePolygonCompletion = useCallback((polygon: google.maps.Polygon, points: BoundaryPoint[]) => {
    const validation = validatePolygon(points);

    if (!validation.isValid) {
      setAlert({ message: validation.error!, severity: 'error' });
      polygon.setMap(null);
      return;
    }

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
  }, [boundaries]);

  useEffect(() => {
    return () => {
      stopDrawing();
    };
  }, [stopDrawing]);

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
    if (polygons.length < 2) return polygons;
    try {
      // Convert to GeoJSON features with reference back to index
      const features: Array<{ feature: Feature<Polygon>; boundary: Boundary }> = polygons.map(p => ({
        feature: turfPolygon([
          p.points.map(pt => [pt.lng, pt.lat])
        ], { id: p.id, name: p.name }),
        boundary: p
      }));

      const consumed = new Set<number>();
      const merged: Boundary[] = [];

      for (let i = 0; i < features.length; i++) {
        if (consumed.has(i)) continue;
        let group: Feature<Polygon>[] = [features[i].feature];
        let groupNames: string[] = [features[i].boundary.name];
        consumed.add(i);
        let changed = true;
        while (changed) {
          changed = false;
            for (let j = 0; j < features.length; j++) {
              if (consumed.has(j)) continue;
              // Check intersection with any in group
              if (group.some(g => booleanIntersects(g as any, features[j].feature as any))) {
                group.push(features[j].feature);
                groupNames.push(features[j].boundary.name);
                consumed.add(j);
                changed = true;
              }
            }
        }
        // Union group
        let unionFeature: any = group[0];
        for (let k = 1; k < group.length; k++) {
          try {
            unionFeature = union(unionFeature as any, group[k] as any) || unionFeature;
          } catch (e) {
            console.warn('Union failure within group', e);
          }
        }
        if (unionFeature.geometry.type === 'Polygon') {
          const coords = unionFeature.geometry.coordinates[0].map((c: number[]) => ({ lat: c[1], lng: c[0] }));
          merged.push({
            id: group.length > 1 ? `boundary-merged-${Date.now()}-${merged.length}` : features[i].boundary.id,
            name: group.length > 1 ? `Merged(${groupNames.length}) ${groupNames.slice(0,3).join('+')}${groupNames.length>3?'…':''}` : features[i].boundary.name,
            points: coords,
            area: undefined,
            isValid: true,
            vertices: coords.length
          });
        } else if (unionFeature.geometry.type === 'MultiPolygon') {
          unionFeature.geometry.coordinates.forEach((poly: any, idx: number) => {
            const coords = poly[0].map((c: number[]) => ({ lat: c[1], lng: c[0] }));
            merged.push({
              id: `boundary-merged-${Date.now()}-${merged.length}-${idx}`,
              name: `MergedPart ${idx+1} (${groupNames.length})`,
              points: coords,
              area: undefined,
              isValid: true,
              vertices: coords.length
            });
          });
        }
      }
      return merged;
    } catch (e) {
      console.warn('Polygon merging error', e);
      return polygons;
    }
  };

  const stopDrawing = useCallback((preservePolygon: boolean = false) => {
    drawingListenersRef.current.forEach(listener => listener.remove());
    drawingListenersRef.current = [];

    if (!preservePolygon && drawingSessionRef.current.polygon) {
      drawingSessionRef.current.polygon.setMap(null);
    }

    drawingSessionRef.current = {
      polygon: preservePolygon ? drawingSessionRef.current.polygon : null,
      points: []
    };

    if (map) {
      map.setOptions({
        disableDoubleClickZoom: drawingMapOptionsRef.current?.disableDoubleClickZoom ?? false,
        draggableCursor: undefined
      });
    }
    drawingMapOptionsRef.current = null;

    setIsDrawing(false);
  }, [map]);

  const startDrawing = useCallback(() => {
    if (!map) return;

    stopDrawing();

    const polygon = new google.maps.Polygon({
      map,
      paths: [],
      fillColor: '#4CAF50',
      fillOpacity: 0.2,
      strokeColor: '#4CAF50',
      strokeWeight: 2,
      editable: false,
      draggable: false
    });

    drawingSessionRef.current = { polygon, points: [] };
    setIsDrawing(true);

    drawingMapOptionsRef.current = {
      disableDoubleClickZoom: map.get('disableDoubleClickZoom') as boolean | null
    };
    map.setOptions({ disableDoubleClickZoom: true, draggableCursor: 'crosshair' });

    const clickListener = map.addListener('click', (event: google.maps.MapMouseEvent) => {
      const latLng = event.latLng;
      if (!latLng || !drawingSessionRef.current.polygon) return;
      drawingSessionRef.current.points = [...drawingSessionRef.current.points, { lat: latLng.lat(), lng: latLng.lng() }];
      drawingSessionRef.current.polygon.setPaths([drawingSessionRef.current.points]);
    });

    const dblClickListener = map.addListener('dblclick', (event: google.maps.MapMouseEvent) => {
      const domEvt = event.domEvent as MouseEvent | undefined;
      domEvt?.preventDefault?.();

      const session = drawingSessionRef.current;
      if (!session.polygon || session.points.length < 3) {
        return;
      }

      stopDrawing(true);
      handlePolygonCompletion(session.polygon, [...session.points]);
      drawingSessionRef.current = { polygon: null, points: [] };
    });

    const rightClickListener = map.addListener('rightclick', (event: google.maps.MapMouseEvent) => {
      const domEvt = event.domEvent as MouseEvent | undefined;
      domEvt?.preventDefault?.();

      const session = drawingSessionRef.current;
      if (!session.polygon || session.points.length === 0) {
        return;
      }

      session.points = session.points.slice(0, -1);
      session.polygon.setPaths([session.points]);
    });

    drawingListenersRef.current = [clickListener, dblClickListener, rightClickListener];
  }, [map, stopDrawing, handlePolygonCompletion]);

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

      let updatedBoundaries = [...boundaries, newBoundary];
      // Perform merge pass (will preserve non-overlapping polygons)
      const merged = mergeOverlappingPolygons(updatedBoundaries);
      if (merged.length !== updatedBoundaries.length) {
        setAlert({ message: 'Overlapping boundaries merged', severity: 'success' });
      }
      updatedBoundaries = merged;
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
          
          <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
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
                onClick={() => stopDrawing()}
              >
                Cancel
              </Button>
            )}
            <Button
              variant="outlined"
              size="small"
              onClick={() => {
                // Export boundaries to JSON
                const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(boundaries, null, 2));
                const dl = document.createElement('a');
                dl.setAttribute('href', dataStr);
                dl.setAttribute('download', 'boundaries.json');
                dl.click();
              }}
            >Export</Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'application/json';
                input.onchange = (e: any) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = () => {
                    try {
                      const imported = JSON.parse(reader.result as string);
                      if (Array.isArray(imported)) {
                        onBoundariesChange(imported.map((b: any, idx: number) => ({
                          id: b.id || `boundary-import-${idx}-${Date.now()}`,
                          name: b.name || `Imported Boundary ${idx+1}`,
                          points: b.points || b.coordinates || [],
                          area: b.area,
                          isValid: true,
                          vertices: (b.points || b.coordinates || []).length
                        })));
                        setAlert({ message: 'Boundaries imported', severity: 'success' });
                      }
                    } catch (err) {
                      setAlert({ message: 'Import failed: invalid file', severity: 'error' });
                    }
                  };
                  reader.readAsText(file);
                };
                input.click();
              }}
            >Import</Button>
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

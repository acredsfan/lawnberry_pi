import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  LinearProgress,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Stop as StopIcon,
  Battery20 as BatteryIcon,
  Timer as TimerIcon,
  Speed as SpeedIcon,
  Straighten as DistanceIcon,
  TrendingUp as EfficiencyIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon
} from '@mui/icons-material';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store/store';
import { MapProvider } from '../../types';

interface ProgressData {
  sessionId: string;
  startTime: Date;
  endTime?: Date;
  totalArea: number;
  coveredArea: number;
  coveragePercentage: number;
  timeElapsed: number;
  estimatedTimeRemaining?: number;
  batteryUsed: number;
  averageSpeed: number;
  distanceTraveled: number;
  efficiency: number;
  currentActivity: string;
  pathHistory: PathPoint[];
}

interface PathPoint {
  lat: number;
  lng: number;
  timestamp: Date;
  activity: 'idle' | 'moving' | 'mowing' | 'turning' | 'avoiding';
  heading: number;
  speed: number;
  batteryLevel: number;
}

interface ProgressTrackerProps {
  mapProvider: MapProvider;
  map: google.maps.Map | L.Map | null;
  robotPosition?: { lat: number; lng: number };
  onVisibilityChange?: (visible: boolean) => void;
}

const ProgressTracker: React.FC<ProgressTrackerProps> = ({
  mapProvider,
  map,
  robotPosition,
  onVisibilityChange
}) => {
  const dispatch = useDispatch();
  const { status, isConnected } = useSelector((state: RootState) => state.mower);
  
  const [progressData, setProgressData] = useState<ProgressData | null>(null);
  const [isVisible, setIsVisible] = useState(true);
  const [updateFrequency, setUpdateFrequency] = useState(10000); // 10 seconds default
  const [pathOverlay, setPathOverlay] = useState<google.maps.Polyline | L.Polyline | null>(null);
  const [coverageOverlay, setCoverageOverlay] = useState<google.maps.Polygon[] | L.Polygon[] | null>(null);
  const [robotMarker, setRobotMarker] = useState<google.maps.Marker | L.Marker | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pathHistoryRef = useRef<PathPoint[]>([]);

  // Adaptive update frequency based on robot state
  useEffect(() => {
    if (!status) return;
    
    const isActive = status.state === 'mowing' || status.state === 'returning';
    const newFrequency = isActive ? 1000 : 10000; // 1s when active, 10s when idle
    
    if (newFrequency !== updateFrequency) {
      setUpdateFrequency(newFrequency);
    }
  }, [status?.state, updateFrequency]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!isConnected) return;

    const connectWebSocket = () => {
      const wsUrl = import.meta.env.DEV 
        ? 'ws://localhost:9002' 
        : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:9002`;
      
      wsRef.current = new WebSocket(wsUrl);
      
      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };
      
      wsRef.current.onopen = () => {
        console.log('Progress tracking WebSocket connected');
        // Subscribe to progress tracking topics
        wsRef.current?.send(JSON.stringify({
          action: 'subscribe',
          topics: ['mower/progress', 'navigation/position', 'mower/path']
        }));
      };
      
      wsRef.current.onerror = (error) => {
        console.error('Progress tracking WebSocket error:', error);
      };
      
      wsRef.current.onclose = () => {
        console.log('Progress tracking WebSocket disconnected');
        // Reconnect after delay
        setTimeout(connectWebSocket, 3000);
      };
    };

    connectWebSocket();

    return () => {
      wsRef.current?.close();
    };
  }, [isConnected]);

  // Handle WebSocket messages
  const handleWebSocketMessage = useCallback((message: any) => {
    switch (message.topic) {
      case 'mower/progress':
        updateProgressData(message.payload);
        break;
      case 'navigation/position':
        updateRobotPosition(message.payload);
        break;
      case 'mower/path':
        updatePathHistory(message.payload);
        break;
    }
  }, []);

  // Update progress data
  const updateProgressData = useCallback((payload: any) => {
    setProgressData(prev => ({
      sessionId: payload.sessionId || prev?.sessionId || generateSessionId(),
      startTime: payload.startTime ? new Date(payload.startTime) : prev?.startTime || new Date(),
      endTime: payload.endTime ? new Date(payload.endTime) : undefined,
      totalArea: payload.totalArea || prev?.totalArea || 0,
      coveredArea: payload.coveredArea || 0,
      coveragePercentage: payload.coveragePercentage || 0,
      timeElapsed: payload.timeElapsed || 0,
      estimatedTimeRemaining: payload.estimatedTimeRemaining,
      batteryUsed: payload.batteryUsed || 0,
      averageSpeed: payload.averageSpeed || 0,
      distanceTraveled: payload.distanceTraveled || 0,
      efficiency: payload.efficiency || 0,
      currentActivity: payload.currentActivity || 'idle',
      pathHistory: prev?.pathHistory || []
    }));
  }, []);

  // Update robot position and marker
  const updateRobotPosition = useCallback((payload: any) => {
    if (!map || !payload.position) return;

    const position = { lat: payload.position.lat, lng: payload.position.lng };
    
    if (mapProvider === 'google' && map instanceof google.maps.Map) {
      if (robotMarker && robotMarker instanceof google.maps.Marker) {
        robotMarker.setPosition(position);
      } else {
        const marker = new google.maps.Marker({
          position,
          map,
          title: 'Robot Position',
          icon: {
            url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(`
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="8" fill="#2196F3" stroke="#fff" stroke-width="2"/>
                <circle cx="12" cy="12" r="3" fill="#fff"/>
              </svg>
            `),
            scaledSize: new google.maps.Size(24, 24),
            anchor: new google.maps.Point(12, 12)
          }
        });
        setRobotMarker(marker);
      }
    } else if (mapProvider === 'openstreetmap' && map && 'setView' in map) {
      // Leaflet implementation
      if (robotMarker && 'setLatLng' in robotMarker) {
        (robotMarker as any).setLatLng([position.lat, position.lng]);
      } else {
        const L = (window as any).L;
        if (L) {
          const marker = L.circleMarker([position.lat, position.lng], {
            radius: 8,
            fillColor: '#2196F3',
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.8
          }).addTo(map);
          setRobotMarker(marker);
        }
      }
    }
  }, [map, mapProvider, robotMarker]);

  // Update path history and visualization
  const updatePathHistory = useCallback((payload: any) => {
    if (!payload.position) return;

    const newPoint: PathPoint = {
      lat: payload.position.lat,
      lng: payload.position.lng,
      timestamp: new Date(payload.timestamp || Date.now()),
      activity: payload.activity || 'idle',
      heading: payload.heading || 0,
      speed: payload.speed || 0,
      batteryLevel: payload.batteryLevel || 0
    };

    pathHistoryRef.current.push(newPoint);
    
    // Limit path history to prevent memory issues (keep last 1000 points)
    if (pathHistoryRef.current.length > 1000) {
      pathHistoryRef.current = pathHistoryRef.current.slice(-1000);
    }

    updatePathVisualization();
  }, []);

  // Update path visualization on map
  const updatePathVisualization = useCallback(() => {
    if (!map || pathHistoryRef.current.length < 2) return;

    // Remove existing path overlay
    if (pathOverlay) {
      if ('setMap' in pathOverlay) {
        (pathOverlay as google.maps.Polyline).setMap(null);
      } else if ('remove' in pathOverlay) {
        (pathOverlay as any).remove();
      }
    }

    const pathCoords = pathHistoryRef.current.map(point => ({ lat: point.lat, lng: point.lng }));

    if (mapProvider === 'google' && map instanceof google.maps.Map) {
      const polyline = new google.maps.Polyline({
        path: pathCoords,
        geodesic: true,
        strokeColor: '#4CAF50',
        strokeOpacity: 0.8,
        strokeWeight: 3,
        map
      });
      setPathOverlay(polyline);
    } else if (mapProvider === 'openstreetmap' && map && 'setView' in map) {
      const L = (window as any).L;
      if (L) {
        const latlngs = pathHistoryRef.current.map(point => [point.lat, point.lng]);
        const polyline = L.polyline(latlngs, {
          color: '#4CAF50',
          weight: 3,
          opacity: 0.8
        }).addTo(map);
        setPathOverlay(polyline);
      }
    }
  }, [map, mapProvider, pathOverlay]);

  // Generate unique session ID
  const generateSessionId = () => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  };

  // Format duration
  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Toggle visibility
  const handleVisibilityToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    const visible = event.target.checked;
    setIsVisible(visible);
    onVisibilityChange?.(visible);
  };

  if (!isVisible || !progressData) {
    return (
      <Box sx={{ position: 'absolute', top: 16, right: 16, zIndex: 1000 }}>
        <FormControlLabel
          control={<Switch checked={isVisible} onChange={handleVisibilityToggle} />}
          label="Show Progress"
        />
      </Box>
    );
  }

  return (
    <Box sx={{ position: 'absolute', top: 16, right: 16, zIndex: 1000, width: 400 }}>
      <Paper elevation={3} sx={{ p: 2 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">Mowing Progress</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip 
              label={progressData.currentActivity}
              color={progressData.currentActivity === 'mowing' ? 'success' : 'default'}
              size="small"
            />
            <FormControlLabel
              control={<Switch checked={isVisible} onChange={handleVisibilityToggle} size="small" />}
              label=""
            />
          </Box>
        </Box>

        {/* Coverage Progress */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2">Coverage</Typography>
            <Typography variant="body2" fontWeight="bold">
              {progressData.coveragePercentage.toFixed(1)}%
            </Typography>
          </Box>
          <LinearProgress 
            variant="determinate" 
            value={progressData.coveragePercentage} 
            sx={{ height: 8, borderRadius: 4 }}
          />
          <Typography variant="caption" color="text.secondary">
            {progressData.coveredArea.toFixed(0)} m² of {progressData.totalArea.toFixed(0)} m²
          </Typography>
        </Box>

        {/* Statistics Grid */}
        <Grid container spacing={1} sx={{ mb: 2 }}>
          <Grid item xs={6}>
            <Card variant="outlined" sx={{ p: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TimerIcon fontSize="small" color="primary" />
                <Box>
                  <Typography variant="caption" color="text.secondary">Time</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {formatDuration(progressData.timeElapsed)}
                  </Typography>
                </Box>
              </Box>
            </Card>
          </Grid>
          <Grid item xs={6}>
            <Card variant="outlined" sx={{ p: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <BatteryIcon fontSize="small" color="primary" />
                <Box>
                  <Typography variant="caption" color="text.secondary">Battery Used</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {progressData.batteryUsed.toFixed(0)}%
                  </Typography>
                </Box>
              </Box>
            </Card>
          </Grid>
          <Grid item xs={6}>
            <Card variant="outlined" sx={{ p: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <SpeedIcon fontSize="small" color="primary" />
                <Box>
                  <Typography variant="caption" color="text.secondary">Avg Speed</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {progressData.averageSpeed.toFixed(1)} m/s
                  </Typography>
                </Box>
              </Box>
            </Card>
          </Grid>
          <Grid item xs={6}>
            <Card variant="outlined" sx={{ p: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <EfficiencyIcon fontSize="small" color="primary" />
                <Box>
                  <Typography variant="caption" color="text.secondary">Efficiency</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {progressData.efficiency.toFixed(1)}%
                  </Typography>
                </Box>
              </Box>
            </Card>
          </Grid>
        </Grid>

        {/* Estimated Time Remaining */}
        {progressData.estimatedTimeRemaining && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Estimated time remaining: {formatDuration(progressData.estimatedTimeRemaining)}
            </Typography>
          </Box>
        )}

        {/* Session Info */}
        <Box sx={{ borderTop: 1, borderColor: 'divider', pt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Session: {progressData.sessionId}
          </Typography>
          <br />
          <Typography variant="caption" color="text.secondary">
            Started: {progressData.startTime.toLocaleTimeString()}
          </Typography>
        </Box>
      </Paper>
    </Box>
  );
};

export default ProgressTracker;

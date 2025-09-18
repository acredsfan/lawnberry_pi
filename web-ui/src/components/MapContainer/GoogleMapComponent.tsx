import React, { useRef, useEffect, useState, useCallback } from 'react';
import { MapError, MapUsageLevel, YardBoundary, MapProvider } from '../../types';
import { mapService } from '../../services/mapService';

interface GoogleMapComponentProps {
  center: { lat: number; lng: number };
  zoom: number;
  usageLevel: MapUsageLevel;
  isOffline: boolean;
  onError: (error: MapError) => void;
  style?: React.CSSProperties;
  children?: React.ReactNode;
  boundaries?: YardBoundary[];
  noGoZones?: YardBoundary[];
  homeLocation?: { lat: number; lng: number };
  robotPosition?: { lat: number; lng: number; heading?: number };
  isDrawingMode?: boolean;
  drawingType?: 'boundary' | 'no-go' | 'home';
  onBoundaryComplete?: (coordinates: Array<{ lat: number; lng: number }>) => void;
  onNoGoZoneComplete?: (coordinates: Array<{ lat: number; lng: number }>) => void;
  onHomeLocationSet?: (coordinates: { lat: number; lng: number }) => void;
  showMowingProgress?: boolean;
  mowingPath?: Array<{ lat: number; lng: number }>;
  coveredAreas?: Array<{ lat: number; lng: number }>;
  onMapReady?: (map: google.maps.Map) => void;
  geofenceViolation?: boolean;
  geofenceInNoGo?: boolean;
}

const GoogleMapComponent: React.FC<GoogleMapComponentProps> = ({
  center,
  zoom,
  usageLevel,
  isOffline,
  onError,
  style,
  children,
  boundaries = [],
  noGoZones = [],
  homeLocation,
  robotPosition,
  isDrawingMode = false,
  drawingType = 'boundary',
  onBoundaryComplete,
  onNoGoZoneComplete,
  onHomeLocationSet,
  showMowingProgress = false,
  mowingPath = [],
  coveredAreas = []
  , onMapReady
  , geofenceViolation
  , geofenceInNoGo
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<google.maps.Map | null>(null);
  const drawingManagerRef = useRef<google.maps.drawing.DrawingManager | null>(null);
  const boundaryPolygonsRef = useRef<google.maps.Polygon[]>([]);
  const noGoZonePolygonsRef = useRef<google.maps.Polygon[]>([]);
  const homeMarkerRef = useRef<google.maps.Marker | null>(null);
  const robotMarkerRef = useRef<google.maps.Marker | null>(null);
  const mowingPathRef = useRef<google.maps.Polyline | null>(null);
  const coveredAreasRef = useRef<google.maps.Polygon[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  const [customControls, setCustomControls] = useState<{
    drawingToolbar?: HTMLElement;
    offlineIndicator?: HTMLElement;
    followBtn?: HTMLButtonElement;
  }>({});
  const [autoFollow, setAutoFollow] = useState(true);
  const autoFollowRef = useRef(true);
  const programmaticZoomRef = useRef(false);
  const programmaticCenterRef = useRef(false);
  const lastAppliedZoomRef = useRef<number | null>(null);
  const lastAppliedCenterRef = useRef<{ lat: number; lng: number } | null>(null);

  const createCustomMapStyles = useCallback((): google.maps.MapTypeStyle[] => {
    // LawnBerryPi branded map styles
    return [
      {
        featureType: 'landscape',
        elementType: 'geometry.fill',
        stylers: [{ color: '#e8f5e8' }] // Light green for grass areas
      },
      {
        featureType: 'poi.park',
        elementType: 'geometry.fill',
        stylers: [{ color: '#c8e6c9' }] // Slightly darker green for parks
      },
      {
        featureType: 'water',
        elementType: 'geometry.fill',
        stylers: [{ color: '#81c784' }] // LawnBerry theme green for water
      },
      {
        featureType: 'road',
        elementType: 'geometry.stroke',
        stylers: [{ color: '#4caf50' }] // Green road borders
      }
    ];
  }, []);

  const baseMapOptions = React.useMemo((): google.maps.MapOptions => {
    const usageSettings = mapService.getUsageLevelSettings(usageLevel);

    const options: google.maps.MapOptions = {
      styles: createCustomMapStyles(),
      mapTypeControl: true,
      mapTypeControlOptions: {
        style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
        position: google.maps.ControlPosition.TOP_RIGHT,
        mapTypeIds: [
          google.maps.MapTypeId.ROADMAP,
          google.maps.MapTypeId.SATELLITE,
          google.maps.MapTypeId.HYBRID,
          google.maps.MapTypeId.TERRAIN
        ]
      },
      zoomControl: true,
      zoomControlOptions: {
        position: google.maps.ControlPosition.RIGHT_BOTTOM
      },
      streetViewControl: false,
      fullscreenControl: true,
      fullscreenControlOptions: {
        position: google.maps.ControlPosition.RIGHT_TOP
      },
      gestureHandling: 'cooperative',
      clickableIcons: usageSettings.enableAllFeatures,
      disableDefaultUI: !usageSettings.enableAllFeatures,
      backgroundColor: 'transparent'
    };

    if (!usageSettings.enableAllFeatures) {
      options.zoomControl = true;
      options.mapTypeControl = true;
      options.fullscreenControl = true;
      options.disableDefaultUI = false;
    }

    return options;
  }, [usageLevel, createCustomMapStyles]);

  const getInitialMapOptions = useCallback((): google.maps.MapOptions => ({
    ...baseMapOptions,
    center,
    zoom
  }), [baseMapOptions, center, zoom]);

const initializeDrawingManager = useCallback(async (map: google.maps.Map) => {
    if (!window.google?.maps?.drawing) {
      console.warn('Google Maps Drawing library not loaded');
      return;
    }

    const drawingManager = new google.maps.drawing.DrawingManager({
      drawingMode: null,
      drawingControl: false, // We'll use custom controls
      polygonOptions: {
        fillColor: '#4caf50',
        fillOpacity: 0.3,
        strokeColor: '#4caf50',
        strokeWeight: 2,
        clickable: true,
        editable: true,
        draggable: false
      },
      circleOptions: {
        fillColor: '#f44336',
        fillOpacity: 0.3,
        strokeColor: '#f44336',
        strokeWeight: 2,
        clickable: true,
        editable: true,
        draggable: false
      }
    });

    drawingManager.setMap(map);
    drawingManagerRef.current = drawingManager;

    // Handle completed shapes
    drawingManager.addListener('polygoncomplete', (polygon: google.maps.Polygon) => {
      const path = polygon.getPath();
      const coordinates = path.getArray().map(latLng => ({
        lat: latLng.lat(),
        lng: latLng.lng()
      }));

      if (drawingType === 'boundary' && onBoundaryComplete) {
        onBoundaryComplete(coordinates);
      } else if (drawingType === 'no-go' && onNoGoZoneComplete) {
        onNoGoZoneComplete(coordinates);
      }

      // Reset drawing mode after completion
      drawingManager.setDrawingMode(null);
    });

    drawingManager.addListener('circlecomplete', (circle: google.maps.Circle) => {
      const center = circle.getCenter();
      const radius = circle.getRadius();
      
      // Convert circle to polygon for consistency
      const coordinates = generateCirclePolygon(center!, radius);
      
      if (drawingType === 'no-go' && onNoGoZoneComplete) {
        onNoGoZoneComplete(coordinates);
      }

      // Remove the circle and reset drawing mode
      circle.setMap(null);
      drawingManager.setDrawingMode(null);
    });
  }, [drawingType, onBoundaryComplete, onNoGoZoneComplete]);

  const generateCirclePolygon = (center: google.maps.LatLng, radius: number): Array<{ lat: number; lng: number }> => {
    const points: Array<{ lat: number; lng: number }> = [];
    const numPoints = 32;
    
    for (let i = 0; i < numPoints; i++) {
      const angle = (i * 360 / numPoints) * Math.PI / 180;
      const lat = center.lat() + (radius / 111000) * Math.cos(angle);
      const lng = center.lng() + (radius / (111000 * Math.cos(center.lat() * Math.PI / 180))) * Math.sin(angle);
      points.push({ lat, lng });
    }
    
    return points;
  };

  const initializeCustomControls = useCallback((map: google.maps.Map) => {
    // Create drawing toolbar
    const drawingToolbar = document.createElement('div');
    drawingToolbar.className = 'drawing-toolbar';
    drawingToolbar.style.cssText = `
      background: white;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.2);
      margin: 10px;
      padding: 8px;
      display: flex;
      gap: 8px;
      font-family: Arial, sans-serif;
    `;

    // Create tool buttons
    const createToolButton = (text: string, action: () => void, active = false) => {
      const button = document.createElement('button');
      button.textContent = text;
      button.style.cssText = `
        padding: 8px 12px;
        border: 1px solid #4caf50;
        background: ${active ? '#4caf50' : 'white'};
        color: ${active ? 'white' : '#4caf50'};
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
        transition: all 0.2s;
      `;
      button.addEventListener('click', action);
      return button;
    };

    const boundaryBtn = createToolButton('Draw Boundary', () => {
      if (drawingManagerRef.current) {
        drawingManagerRef.current.setDrawingMode(google.maps.drawing.OverlayType.POLYGON);
      }
    });

    const noGoBtn = createToolButton('Draw No-Go Zone', () => {
      if (drawingManagerRef.current) {
        drawingManagerRef.current.setDrawingMode(google.maps.drawing.OverlayType.CIRCLE);
      }
    });

    const homeBtn = createToolButton('Set Home', () => {
      // Enable click mode for home location
      map.setOptions({ draggableCursor: 'crosshair' });
    });

    const clearBtn = createToolButton('Clear All', () => {
      clearAllOverlays();
    });

    drawingToolbar.appendChild(boundaryBtn);
    drawingToolbar.appendChild(noGoBtn);
    drawingToolbar.appendChild(homeBtn);
    drawingToolbar.appendChild(clearBtn);

    const followBtn = createToolButton(autoFollowRef.current ? 'Following' : 'Follow Robot', () => {
      autoFollowRef.current = true;
      setAutoFollow(true);
      if (mapInstanceRef.current) {
        const target = robotPosition || center;
        programmaticCenterRef.current = true;
        mapInstanceRef.current.panTo(target);
        lastAppliedCenterRef.current = { lat: target.lat, lng: target.lng };
        if (typeof zoom === 'number') {
          programmaticZoomRef.current = true;
          mapInstanceRef.current.setZoom(zoom);
          lastAppliedZoomRef.current = zoom;
        }
      }
    }, autoFollowRef.current);

    drawingToolbar.appendChild(followBtn);

    map.controls[google.maps.ControlPosition.TOP_CENTER].push(drawingToolbar);

    // Create offline indicator
    const offlineIndicator = document.createElement('div');
    offlineIndicator.style.cssText = `
      background: #f44336;
      color: white;
      padding: 8px 16px;
      border-radius: 4px;
      margin: 10px;
      font-family: Arial, sans-serif;
      font-size: 12px;
      display: ${isOffline ? 'block' : 'none'};
    `;
    offlineIndicator.textContent = 'Offline Mode - Limited Functionality';
    
    map.controls[google.maps.ControlPosition.TOP_RIGHT].push(offlineIndicator);

    setCustomControls({ drawingToolbar, offlineIndicator, followBtn });
  }, [isOffline, center, zoom, clearAllOverlays, robotPosition]);

  useEffect(() => {
    autoFollowRef.current = autoFollow;
    if (customControls.followBtn) {
      customControls.followBtn.textContent = autoFollow ? 'Following' : 'Follow Robot';
      customControls.followBtn.style.background = autoFollow ? '#4caf50' : 'white';
      customControls.followBtn.style.color = autoFollow ? 'white' : '#4caf50';
    }
  }, [autoFollow, customControls.followBtn]);

  const clearAllOverlays = useCallback(() => {
    // Clear boundary polygons
    boundaryPolygonsRef.current.forEach(polygon => polygon.setMap(null));
    boundaryPolygonsRef.current = [];

    // Clear no-go zone polygons
    noGoZonePolygonsRef.current.forEach(polygon => polygon.setMap(null));
    noGoZonePolygonsRef.current = [];

    // Clear home marker
    if (homeMarkerRef.current) {
      homeMarkerRef.current.setMap(null);
      homeMarkerRef.current = null;
    }

    // Clear mowing path
    if (mowingPathRef.current) {
      mowingPathRef.current.setMap(null);
      mowingPathRef.current = null;
    }

    // Clear covered areas
    coveredAreasRef.current.forEach(polygon => polygon.setMap(null));
    coveredAreasRef.current = [];
  }, []);

  const setupMapEventListeners = useCallback((map: google.maps.Map) => {
    // Handle click for home location setting
    map.addListener('click', (event: google.maps.MapMouseEvent) => {
      if (map.get('draggableCursor') === 'crosshair' && onHomeLocationSet) {
        const coordinates = {
          lat: event.latLng!.lat(),
          lng: event.latLng!.lng()
        };
        onHomeLocationSet(coordinates);
        map.setOptions({ draggableCursor: undefined });
      }
    });

    map.addListener('dragstart', () => {
      autoFollowRef.current = false;
      setAutoFollow(false);
    });

    map.addListener('zoom_changed', () => {
      if (programmaticZoomRef.current) {
        programmaticZoomRef.current = false;
        return;
      }
      autoFollowRef.current = false;
      setAutoFollow(false);
    });

    map.addListener('idle', () => {
      programmaticCenterRef.current = false;
      programmaticZoomRef.current = false;
    });
  }, [onHomeLocationSet]);

  const updateBoundaries = useCallback(() => {
    if (!mapInstanceRef.current) return;

    // Clear existing boundary polygons
    boundaryPolygonsRef.current.forEach(polygon => polygon.setMap(null));
    boundaryPolygonsRef.current = [];

    // Add new boundary polygons
  boundaries.forEach(boundary => {
      const polygon = new google.maps.Polygon({
    paths: (boundary as any).coordinates?.map((coord: any) => ({ lat: coord.lat, lng: coord.lng })) || (boundary as any).points?.map((p: any) => ({ lat: p.lat, lng: p.lng })),
  strokeColor: geofenceViolation ? '#f44336' : '#4caf50',
  strokeOpacity: geofenceViolation ? 1.0 : 0.8,
  strokeWeight: geofenceViolation ? 3 : 2,
  fillColor: geofenceViolation ? '#f44336' : '#4caf50',
  fillOpacity: geofenceViolation ? 0.15 : 0.1,
        editable: true,
        draggable: false
      });

      polygon.setMap(mapInstanceRef.current);
      boundaryPolygonsRef.current.push(polygon);
    });
  }, [boundaries, geofenceViolation]);

  const updateNoGoZones = useCallback(() => {
    if (!mapInstanceRef.current) return;

    // Clear existing no-go zone polygons
    noGoZonePolygonsRef.current.forEach(polygon => polygon.setMap(null));
    noGoZonePolygonsRef.current = [];

    // Add new no-go zone polygons
  noGoZones.forEach(zone => {
      const polygon = new google.maps.Polygon({
    paths: (zone as any).coordinates?.map((coord: any) => ({ lat: coord.lat, lng: coord.lng })) || (zone as any).points?.map((p: any) => ({ lat: p.lat, lng: p.lng })),
  strokeColor: geofenceInNoGo ? '#ff1744' : '#f44336',
  strokeOpacity: geofenceInNoGo ? 1.0 : 0.9,
  strokeWeight: geofenceInNoGo ? 3 : 2,
  fillColor: geofenceInNoGo ? '#ff1744' : '#f44336',
  fillOpacity: geofenceInNoGo ? 0.4 : 0.3,
        editable: true,
        draggable: false
      });

      polygon.setMap(mapInstanceRef.current);
      noGoZonePolygonsRef.current.push(polygon);
    });
  }, [noGoZones, geofenceInNoGo]);

  const updateHomeLocation = useCallback(() => {
    if (!mapInstanceRef.current) return;

    // Clear existing home marker
    if (homeMarkerRef.current) {
      homeMarkerRef.current.setMap(null);
      homeMarkerRef.current = null;
    }

    // Add new home marker
    if (homeLocation) {
      const marker = new google.maps.Marker({
        position: homeLocation,
        map: mapInstanceRef.current,
        title: 'Home Base',
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 10,
          fillColor: '#2196f3',
          fillOpacity: 1,
          strokeColor: 'white',
          strokeWeight: 2
        }
      });

      homeMarkerRef.current = marker;
    }
  }, [homeLocation]);

  const updateRobotPosition = useCallback(() => {
    if (!mapInstanceRef.current || !robotPosition) return;

    const icon: google.maps.Symbol = {
      path: 'M12 2C8.13 2 5 5.13 5 9c0 3.87 6.01 11 6.01 11s6.99-7.13 6.99-11c0-3.87-3.13-7-6-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
      fillColor: geofenceViolation ? '#FF1744' : '#FF1493',
      fillOpacity: 0.95,
      strokeColor: geofenceInNoGo ? '#FFEA00' : '#00FFD1',
      strokeWeight: 1.6,
      rotation: robotPosition.heading || 0,
      scale: 1.35,
      anchor: new google.maps.Point(12, 22)
    };

    if (!robotMarkerRef.current) {
      robotMarkerRef.current = new google.maps.Marker({
        position: robotPosition,
        map: mapInstanceRef.current,
        title: 'LawnBerryPi',
        icon,
        zIndex: 1000
      });
    } else {
      robotMarkerRef.current.setPosition(robotPosition);
      robotMarkerRef.current.setIcon(icon);
    }

    if (autoFollowRef.current) {
      programmaticCenterRef.current = true;
      mapInstanceRef.current.panTo(robotPosition);
      lastAppliedCenterRef.current = { lat: robotPosition.lat, lng: robotPosition.lng };
    }
  }, [robotPosition, geofenceViolation, geofenceInNoGo]);

  const updateMowingProgress = useCallback(() => {
    if (!mapInstanceRef.current || !showMowingProgress) return;

    // Clear existing mowing path
    if (mowingPathRef.current) {
      mowingPathRef.current.setMap(null);
      mowingPathRef.current = null;
    }

    // Clear existing covered areas
    coveredAreasRef.current.forEach(polygon => polygon.setMap(null));
    coveredAreasRef.current = [];

    // Add mowing path
    if (mowingPath.length > 0) {
      const polyline = new google.maps.Polyline({
        path: mowingPath,
        geodesic: true,
        strokeColor: '#ff9800',
        strokeOpacity: 1.0,
        strokeWeight: 3
      });

      polyline.setMap(mapInstanceRef.current);
      mowingPathRef.current = polyline;
    }

    // Add covered areas (simplified - in real implementation, these would be actual coverage polygons)
    coveredAreas.forEach(area => {
      const polygon = new google.maps.Polygon({
        paths: [area], // This would be actual coverage polygon in real implementation
        strokeColor: '#4caf50',
        strokeOpacity: 0.3,
        strokeWeight: 1,
        fillColor: '#4caf50',
        fillOpacity: 0.1
      });

      polygon.setMap(mapInstanceRef.current);
      coveredAreasRef.current.push(polygon);
    });
  }, [showMowingProgress, mowingPath, coveredAreas]);

  const initializeMap = useCallback(async () => {
    if (!mapRef.current || mapInstanceRef.current) return;

    try {
      // Ensure Google Maps is loaded
      if (!window.google || !window.google.maps) {
        throw new Error('Google Maps API not loaded');
      }

      const mapOptions = getInitialMapOptions();
      const map = new google.maps.Map(mapRef.current, mapOptions);
      
      mapInstanceRef.current = map;
      
      // Initialize drawing manager
      await initializeDrawingManager(map);
      
      // Initialize custom controls
      initializeCustomControls(map);
      
      // Setup map event listeners
      setupMapEventListeners(map);
      
  setIsInitialized(true);
  onMapReady?.(map);

      // Add error handling for map tiles
      map.addListener('tilesloaded', () => {
        // Map tiles loaded successfully
      });

      // Handle offline mode
      if (isOffline) {
        const offlineOverlay = document.createElement('div');
        offlineOverlay.style.cssText = `
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          background: rgba(0,0,0,0.8);
          color: white;
          padding: 10px 20px;
          border-radius: 4px;
          z-index: 1000;
          font-family: Arial, sans-serif;
        `;
        offlineOverlay.textContent = 'Offline Mode - Using Cached Tiles';
        mapRef.current.appendChild(offlineOverlay);
      }

    } catch (error) {
      const mapError = mapService.createMapError(
        'generic',
        error instanceof Error ? error.message : 'Failed to initialize Google Maps',
        'google' as MapProvider,
        true
      );
      onError(mapError);
    }
  }, [getInitialMapOptions, isOffline, onError, initializeDrawingManager, initializeCustomControls, setupMapEventListeners]);

  // Initialize map on mount
  useEffect(() => {
    initializeMap();
  }, [initializeMap]);

  // Update map center and zoom when props change
  useEffect(() => {
    if (!mapInstanceRef.current || !isInitialized || !autoFollowRef.current) return;

    const desiredCenter = { lat: center.lat, lng: center.lng };
    const needsCenter =
      !lastAppliedCenterRef.current ||
      Math.abs(lastAppliedCenterRef.current.lat - desiredCenter.lat) > 1e-6 ||
      Math.abs(lastAppliedCenterRef.current.lng - desiredCenter.lng) > 1e-6;

    if (needsCenter) {
      programmaticCenterRef.current = true;
      mapInstanceRef.current.panTo(desiredCenter);
      lastAppliedCenterRef.current = desiredCenter;
    }

    if (typeof zoom === 'number') {
      const currentZoom = mapInstanceRef.current.getZoom();
      if (currentZoom !== zoom) {
        programmaticZoomRef.current = true;
        mapInstanceRef.current.setZoom(zoom);
        lastAppliedZoomRef.current = zoom;
      }
    }
  }, [center.lat, center.lng, zoom, isInitialized]);

  // Update map options when usage level changes
  useEffect(() => {
    if (mapInstanceRef.current && isInitialized) {
      mapInstanceRef.current.setOptions(baseMapOptions);
    }
  }, [baseMapOptions, isInitialized]);

  // Handle quota exceeded errors
  useEffect(() => {
    const handleQuotaExceeded = () => {
      const quotaError = mapService.createMapError(
        'quota_exceeded',
        'Google Maps API quota exceeded. Switching to OpenStreetMap.',
        'google' as MapProvider,
        true
      );
      onError(quotaError);
    };

    // Listen for quota exceeded errors (these come from the Google Maps API)
    const script = document.querySelector('script[src*="maps.googleapis.com"]');
    if (script) {
      script.addEventListener('error', handleQuotaExceeded);
      return () => script.removeEventListener('error', handleQuotaExceeded);
    }
  }, [onError]);
  
  // Effect hooks for updating map elements
  useEffect(() => {
    if (isInitialized) {
      updateBoundaries();
    }
  }, [boundaries, isInitialized, updateBoundaries]);

  useEffect(() => {
    if (isInitialized) {
      updateNoGoZones();
    }
  }, [noGoZones, isInitialized, updateNoGoZones]);

  useEffect(() => {
    if (isInitialized) {
      updateHomeLocation();
    }
  }, [homeLocation, isInitialized, updateHomeLocation]);

  useEffect(() => {
    if (isInitialized) {
      updateRobotPosition();
    }
  }, [robotPosition, isInitialized, updateRobotPosition]);

  useEffect(() => {
    if (isInitialized) {
      updateMowingProgress();
    }
  }, [showMowingProgress, mowingPath, coveredAreas, isInitialized, updateMowingProgress]);

  useEffect(() => {
    if (customControls.offlineIndicator) {
      customControls.offlineIndicator.style.display = isOffline ? 'block' : 'none';
    }
  }, [isOffline, customControls.offlineIndicator]);

  useEffect(() => {
    if (!mapRef.current || !window.ResizeObserver) return;

    const observer = new ResizeObserver(() => {
      if (!mapInstanceRef.current) return;
      google.maps.event.trigger(mapInstanceRef.current, 'resize');
      if (autoFollowRef.current && lastAppliedCenterRef.current) {
        programmaticCenterRef.current = true;
        mapInstanceRef.current.panTo(lastAppliedCenterRef.current);
      }
    });

    observer.observe(mapRef.current);
    return () => observer.disconnect();
  }, [isInitialized]);

  useEffect(() => {
    if (drawingManagerRef.current && isDrawingMode) {
      const mode = drawingType === 'boundary' 
        ? google.maps.drawing.OverlayType.POLYGON 
        : drawingType === 'no-go'
        ? google.maps.drawing.OverlayType.CIRCLE
        : null;
      
      drawingManagerRef.current.setDrawingMode(mode);
    } else if (drawingManagerRef.current) {
      drawingManagerRef.current.setDrawingMode(null);
    }
  }, [isDrawingMode, drawingType]);

  return (
    <div
      ref={mapRef}
      style={{
        width: '100%',
        height: '100%',
        ...style
      }}
  data-geofence-violation={geofenceViolation ? '1' : '0'}
  data-geofence-in-nogo={geofenceInNoGo ? '1' : '0'}
    >
      {/* Inline style for geofence pulse (scoped by data attr) */}
      <style>{`
        [data-geofence-violation="1"] canvas + div { /* heuristic: after tiles layer */ }
        [data-geofence-violation="1"] .gm-style .pulse-boundary {
          animation: lbPulse 1.2s ease-in-out infinite;
        }
        @keyframes lbPulse {
          0% { box-shadow: 0 0 0 0 rgba(244,67,54,0.6); }
          70% { box-shadow: 0 0 0 8px rgba(244,67,54,0); }
          100% { box-shadow: 0 0 0 0 rgba(244,67,54,0); }
        }
      `}</style>
      {children}
    </div>
  );
};

export default GoogleMapComponent;

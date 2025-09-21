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
  onBoundaryComplete?: (coordinates: Array<{ lat: number; lng: number }>) => void;
  onNoGoZoneComplete?: (coordinates: Array<{ lat: number; lng: number }>) => void;
  onHomeLocationSet?: (coordinates: { lat: number; lng: number }) => void;
  showMowingProgress?: boolean;
  mowingPath?: Array<{ lat: number; lng: number }>;
  coveredAreas?: Array<{ lat: number; lng: number }>;
  onMapReady?: (map: google.maps.Map) => void;
  geofenceViolation?: boolean;
  geofenceInNoGo?: boolean;
  onClearAll?: () => void;
  onBoundaryUpdate?: (id: string, coordinates: Array<{ lat: number; lng: number }>) => void;
  onNoGoZoneUpdate?: (id: string, coordinates: Array<{ lat: number; lng: number }>) => void;
}

const ROBOT_ICON_URL = new URL('../../assets/LawnBerryPi_icon2.png', import.meta.url).href;

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
  onBoundaryComplete,
  onNoGoZoneComplete,
  onHomeLocationSet,
  showMowingProgress = false,
  mowingPath = [],
  coveredAreas = []
  , onMapReady
  , geofenceViolation
  , geofenceInNoGo
  , onClearAll
  , onBoundaryUpdate
  , onNoGoZoneUpdate
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<google.maps.Map | null>(null);
  const boundaryPolygonsRef = useRef<google.maps.Polygon[]>([]);
  const noGoZonePolygonsRef = useRef<google.maps.Polygon[]>([]);
  const homeMarkerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null);
  const legacyHomeMarkerRef = useRef<google.maps.Marker | null>(null);
  const robotMarkerRef = useRef<{
    marker: google.maps.marker.AdvancedMarkerElement;
    element: HTMLElement;
    arrow: HTMLElement;
  } | null>(null);
  const legacyRobotMarkerRef = useRef<google.maps.Marker | null>(null);
  const mowingPathRef = useRef<google.maps.Polyline | null>(null);
  const coveredAreasRef = useRef<google.maps.Polygon[]>([]);
  const markerLibraryRef = useRef<google.maps.MarkerLibrary | null>(null);
  const drawingSessionRef = useRef<{
    type: 'boundary' | 'no-go' | null;
    polygon: google.maps.Polygon | null;
    path: Array<{ lat: number; lng: number }>;
  }>({ type: null, polygon: null, path: [] });
  const homePlacementRef = useRef(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const [customControls, setCustomControls] = useState<{
    drawingToolbar?: HTMLElement;
    offlineIndicator?: HTMLElement;
    followBtn?: HTMLButtonElement;
    boundaryBtn?: HTMLButtonElement;
    noGoBtn?: HTMLButtonElement;
    homeBtn?: HTMLButtonElement;
    completeBtn?: HTMLButtonElement;
    cancelBtn?: HTMLButtonElement;
  }>({});
  const controlsRef = useRef(customControls);
  const [drawingState, setDrawingState] = useState<{ active: boolean; type: 'boundary' | 'no-go' | null }>({
    active: false,
    type: null
  });
  const [isSettingHome, setIsSettingHome] = useState(false);
  const [autoFollow, setAutoFollow] = useState(false);
  const autoFollowRef = useRef(false);
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

  const refreshControlStates = useCallback(() => {
    const controls = controlsRef.current;
    const session = drawingSessionRef.current;
    if (controls?.completeBtn) {
      controls.completeBtn.disabled = !(session.type && session.path.length >= 3);
    }
    if (controls?.cancelBtn) {
      controls.cancelBtn.disabled = !session.type;
    }
  }, []);

  useEffect(() => {
    controlsRef.current = customControls;
    refreshControlStates();
  }, [customControls, refreshControlStates]);

  useEffect(() => {
    const controls = controlsRef.current;
    const applyActiveStyles = (btn: HTMLButtonElement | undefined, active: boolean, activeColor: string) => {
      if (!btn) return;
      btn.style.background = active ? activeColor : 'white';
      btn.style.color = active ? 'white' : activeColor;
    };

    applyActiveStyles(controls?.boundaryBtn, drawingState.active && drawingState.type === 'boundary', '#4caf50');
    applyActiveStyles(controls?.noGoBtn, drawingState.active && drawingState.type === 'no-go', '#f44336');
    applyActiveStyles(controls?.homeBtn, isSettingHome, '#2196f3');
  }, [drawingState, isSettingHome]);

  const resetDrawingSession = useCallback((removeOverlay: boolean = true) => {
    const session = drawingSessionRef.current;
    if (removeOverlay && session.polygon) {
      session.polygon.setMap(null);
    }
    drawingSessionRef.current = { type: null, polygon: null, path: [] };
    setDrawingState({ active: false, type: null });
    setIsSettingHome(false);
    homePlacementRef.current = false;
    if (mapInstanceRef.current) {
      mapInstanceRef.current.setOptions({ draggableCursor: undefined });
    }
    refreshControlStates();
  }, [refreshControlStates]);

  const beginDrawing = useCallback((type: 'boundary' | 'no-go') => {
    if (!mapInstanceRef.current) return;

    resetDrawingSession();
    homePlacementRef.current = false;
    setIsSettingHome(false);
    const map = mapInstanceRef.current;
    const color = type === 'no-go' ? '#f44336' : '#4caf50';

    const polygon = new google.maps.Polygon({
      map,
      paths: [],
      strokeColor: color,
      strokeOpacity: type === 'no-go' ? 0.9 : 0.8,
      strokeWeight: 2,
      fillColor: color,
      fillOpacity: type === 'no-go' ? 0.3 : 0.15,
      editable: false,
      draggable: false
    });

    drawingSessionRef.current = { type, polygon, path: [] };
    setDrawingState({ active: true, type });
    map.setOptions({ draggableCursor: 'crosshair' });
    refreshControlStates();
  }, [resetDrawingSession, refreshControlStates]);

  const appendDrawingPoint = useCallback((point: { lat: number; lng: number }) => {
    const session = drawingSessionRef.current;
    if (!session.type || !session.polygon) return;

    session.path = [...session.path, point];
    session.polygon.setPaths([session.path]);
    refreshControlStates();
  }, [refreshControlStates]);

  const removeLastDrawingPoint = useCallback(() => {
    const session = drawingSessionRef.current;
    if (!session.type || !session.polygon || session.path.length === 0) return;

    session.path = session.path.slice(0, -1);
    session.polygon.setPaths([session.path]);
    refreshControlStates();
  }, [refreshControlStates]);

  const completeDrawing = useCallback(() => {
    const session = drawingSessionRef.current;
    if (!session.type || session.path.length < 3) return;

    const coordinates = [...session.path];
    if (session.type === 'boundary' && onBoundaryComplete) {
      onBoundaryComplete(coordinates);
    } else if (session.type === 'no-go' && onNoGoZoneComplete) {
      onNoGoZoneComplete(coordinates);
    }

    resetDrawingSession();
  }, [onBoundaryComplete, onNoGoZoneComplete, resetDrawingSession]);

  const cancelDrawing = useCallback(() => {
    resetDrawingSession();
  }, [resetDrawingSession]);

  const ensureMarkerLibrary = useCallback(async () => {
    const config = mapService.getConfig();
    if (!config.mapId) {
      markerLibraryRef.current = null;
      return null;
    }

    if (!markerLibraryRef.current) {
      markerLibraryRef.current = await google.maps.importLibrary('marker') as google.maps.MarkerLibrary;
    }
    return markerLibraryRef.current;
  }, []);

  const clearAllOverlays = useCallback(() => {
    // Clear boundary polygons
    boundaryPolygonsRef.current.forEach(polygon => polygon.setMap(null));
    boundaryPolygonsRef.current = [];

    // Clear no-go zone polygons
    noGoZonePolygonsRef.current.forEach(polygon => polygon.setMap(null));
    noGoZonePolygonsRef.current = [];

    // Clear home markers
    if (homeMarkerRef.current) {
      homeMarkerRef.current.map = null;
      homeMarkerRef.current = null;
    }
    if (legacyHomeMarkerRef.current) {
      legacyHomeMarkerRef.current.setMap(null);
      legacyHomeMarkerRef.current = null;
    }

    // Clear mowing path
    if (mowingPathRef.current) {
      mowingPathRef.current.setMap(null);
      mowingPathRef.current = null;
    }

    // Clear covered areas
    coveredAreasRef.current.forEach(polygon => polygon.setMap(null));
    coveredAreasRef.current = [];

    if (robotMarkerRef.current) {
      robotMarkerRef.current.marker.map = null;
      robotMarkerRef.current = null;
    }
    if (legacyRobotMarkerRef.current) {
      legacyRobotMarkerRef.current.setMap(null);
      legacyRobotMarkerRef.current = null;
    }

    resetDrawingSession();
    homePlacementRef.current = false;
  }, [resetDrawingSession]);

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
      beginDrawing('boundary');
    });

    const noGoBtn = createToolButton('Draw No-Go Zone', () => {
      beginDrawing('no-go');
    });

    const homeBtn = createToolButton('Set Home', () => {
      resetDrawingSession();
      homePlacementRef.current = true;
      setIsSettingHome(true);
      map.setOptions({ draggableCursor: 'crosshair' });
    });

    const clearBtn = createToolButton('Clear All', () => {
      clearAllOverlays();
      onClearAll?.();
    });

    const completeBtn = createToolButton('Finish Shape', () => {
      completeDrawing();
    });
    completeBtn.disabled = true;

    const cancelBtn = createToolButton('Cancel', () => {
      cancelDrawing();
    });
    cancelBtn.disabled = true;

    drawingToolbar.appendChild(boundaryBtn);
    drawingToolbar.appendChild(noGoBtn);
    drawingToolbar.appendChild(homeBtn);
    drawingToolbar.appendChild(clearBtn);
    drawingToolbar.appendChild(completeBtn);
    drawingToolbar.appendChild(cancelBtn);

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

    setCustomControls({ drawingToolbar, offlineIndicator, followBtn, boundaryBtn, noGoBtn, homeBtn, completeBtn, cancelBtn });
  }, [isOffline, center, zoom, clearAllOverlays, robotPosition, beginDrawing, resetDrawingSession, completeDrawing, cancelDrawing]);

  useEffect(() => {
    autoFollowRef.current = autoFollow;
    if (customControls.followBtn) {
      customControls.followBtn.textContent = autoFollow ? 'Following' : 'Follow Robot';
      customControls.followBtn.style.background = autoFollow ? '#4caf50' : 'white';
      customControls.followBtn.style.color = autoFollow ? 'white' : '#4caf50';
    }
  }, [autoFollow, customControls.followBtn]);

  const setupMapEventListeners = useCallback((map: google.maps.Map) => {
    map.addListener('click', (event: google.maps.MapMouseEvent) => {
      const latLng = event.latLng;
      if (!latLng) {
        return;
      }

      if (drawingSessionRef.current.type) {
        appendDrawingPoint({ lat: latLng.lat(), lng: latLng.lng() });
        const domEvt = event.domEvent as MouseEvent | undefined;
        domEvt?.preventDefault?.();
        return;
      }

      if (homePlacementRef.current && onHomeLocationSet) {
        const coordinates = {
          lat: latLng.lat(),
          lng: latLng.lng()
        };
        onHomeLocationSet(coordinates);
        homePlacementRef.current = false;
        setIsSettingHome(false);
        map.setOptions({ draggableCursor: undefined });
        const domEvt = event.domEvent as MouseEvent | undefined;
        domEvt?.preventDefault?.();
      }
    });

    map.addListener('dblclick', (event: google.maps.MapMouseEvent) => {
      if (drawingSessionRef.current.type) {
        const domEvt = event.domEvent as MouseEvent | undefined;
        domEvt?.preventDefault?.();
        completeDrawing();
      }
    });

    map.addListener('rightclick', (event: google.maps.MapMouseEvent) => {
      if (drawingSessionRef.current.type) {
        const domEvt = event.domEvent as MouseEvent | undefined;
        domEvt?.preventDefault?.();
        removeLastDrawingPoint();
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
  }, [appendDrawingPoint, onHomeLocationSet, completeDrawing, removeLastDrawingPoint]);

  const updateBoundaries = useCallback(() => {
    if (!mapInstanceRef.current) return;

    // Clear existing boundary polygons
    boundaryPolygonsRef.current.forEach(polygon => polygon.setMap(null));
    boundaryPolygonsRef.current = [];

    // Add new boundary polygons
    boundaries.forEach(boundary => {
      const coords = (boundary as any).coordinates?.map((coord: any) => ({ lat: coord.lat, lng: coord.lng }))
        || (boundary as any).points?.map((p: any) => ({ lat: p.lat, lng: p.lng }))
        || [];

      const polygon = new google.maps.Polygon({
        paths: coords,
        strokeColor: geofenceViolation ? '#f44336' : '#4caf50',
        strokeOpacity: geofenceViolation ? 1.0 : 0.8,
        strokeWeight: geofenceViolation ? 3 : 2,
        fillColor: geofenceViolation ? '#f44336' : '#4caf50',
        fillOpacity: geofenceViolation ? 0.15 : 0.1,
        editable: true,
        draggable: false
      });

      polygon.setMap(mapInstanceRef.current);

      const boundaryId = (boundary as any).id;
      if (boundaryId && onBoundaryUpdate) {
        const path = polygon.getPath();
        const notifyChange = () => {
          const updated = path.getArray().map(latLng => ({ lat: latLng.lat(), lng: latLng.lng() }));
          onBoundaryUpdate(boundaryId, updated);
        };
        path.addListener('set_at', notifyChange);
        path.addListener('insert_at', notifyChange);
        path.addListener('remove_at', notifyChange);
      }

      boundaryPolygonsRef.current.push(polygon);
    });
  }, [boundaries, geofenceViolation, onBoundaryUpdate]);

  const updateNoGoZones = useCallback(() => {
    if (!mapInstanceRef.current) return;

    // Clear existing no-go zone polygons
    noGoZonePolygonsRef.current.forEach(polygon => polygon.setMap(null));
    noGoZonePolygonsRef.current = [];

    // Add new no-go zone polygons
    noGoZones.forEach(zone => {
      const coords = (zone as any).coordinates?.map((coord: any) => ({ lat: coord.lat, lng: coord.lng }))
        || (zone as any).points?.map((p: any) => ({ lat: p.lat, lng: p.lng }))
        || [];

      const polygon = new google.maps.Polygon({
        paths: coords,
        strokeColor: geofenceInNoGo ? '#ff1744' : '#f44336',
        strokeOpacity: geofenceInNoGo ? 1.0 : 0.9,
        strokeWeight: geofenceInNoGo ? 3 : 2,
        fillColor: geofenceInNoGo ? '#ff1744' : '#f44336',
        fillOpacity: geofenceInNoGo ? 0.4 : 0.3,
        editable: true,
        draggable: false
      });

      polygon.setMap(mapInstanceRef.current);

      const zoneId = (zone as any).id;
      if (zoneId && onNoGoZoneUpdate) {
        const path = polygon.getPath();
        const notifyChange = () => {
          const updated = path.getArray().map(latLng => ({ lat: latLng.lat(), lng: latLng.lng() }));
          onNoGoZoneUpdate(zoneId, updated);
        };
        path.addListener('set_at', notifyChange);
        path.addListener('insert_at', notifyChange);
        path.addListener('remove_at', notifyChange);
      }

      noGoZonePolygonsRef.current.push(polygon);
    });
  }, [noGoZones, geofenceInNoGo, onNoGoZoneUpdate]);

  const updateHomeLocation = useCallback(() => {
    if (!mapInstanceRef.current) return;

    // Clear existing home markers
    if (homeMarkerRef.current) {
      homeMarkerRef.current.map = null;
      homeMarkerRef.current = null;
    }
    if (legacyHomeMarkerRef.current) {
      legacyHomeMarkerRef.current.setMap(null);
      legacyHomeMarkerRef.current = null;
    }

    // Add new home marker
    if (homeLocation) {
      const markerLib = markerLibraryRef.current;
      if (markerLib) {
        const wrapper = document.createElement('div');
        wrapper.style.width = '36px';
        wrapper.style.height = '36px';
        wrapper.style.display = 'flex';
        wrapper.style.alignItems = 'center';
        wrapper.style.justifyContent = 'center';

        const img = document.createElement('img');
        img.src = ROBOT_ICON_URL;
        img.alt = 'Home Base';
        img.style.width = '32px';
        img.style.height = '32px';
        img.style.objectFit = 'contain';
        img.style.filter = 'drop-shadow(0 0 6px rgba(33, 150, 243, 0.6))';

        wrapper.appendChild(img);

        const marker = new markerLib.AdvancedMarkerElement({
          map: mapInstanceRef.current!,
          position: homeLocation,
          title: 'Home Base',
          content: wrapper
        });

        homeMarkerRef.current = marker;
      } else {
        legacyHomeMarkerRef.current = new google.maps.Marker({
          position: homeLocation,
          map: mapInstanceRef.current!,
          title: 'Home Base',
          icon: {
            url: ROBOT_ICON_URL,
            scaledSize: new google.maps.Size(36, 36),
            anchor: new google.maps.Point(18, 18)
          }
        });
      }
    }
  }, [homeLocation]);

  const updateRobotPosition = useCallback(() => {
    if (!mapInstanceRef.current || !robotPosition) return;

    const heading = robotPosition.heading ?? 0;
    const markerLib = markerLibraryRef.current;

    if (markerLib) {
      if (!robotMarkerRef.current) {
        const wrapper = document.createElement('div');
        wrapper.style.width = '40px';
        wrapper.style.height = '40px';
        wrapper.style.display = 'flex';
        wrapper.style.alignItems = 'center';
        wrapper.style.justifyContent = 'center';
        wrapper.style.transform = `rotate(${heading}deg)`;
        wrapper.style.transition = 'transform 0.2s ease-out';
        wrapper.style.filter = 'drop-shadow(0 0 6px rgba(0, 255, 209, 0.6))';

        const img = document.createElement('img');
        img.src = ROBOT_ICON_URL;
        img.alt = 'LawnBerryPi';
        img.style.width = '36px';
        img.style.height = '36px';
        img.style.objectFit = 'contain';

        wrapper.appendChild(img);

        if (legacyRobotMarkerRef.current) {
          legacyRobotMarkerRef.current.setMap(null);
          legacyRobotMarkerRef.current = null;
        }

        const marker = new markerLib.AdvancedMarkerElement({
          map: mapInstanceRef.current,
          position: robotPosition,
          content: wrapper,
          zIndex: 1000
        });

        robotMarkerRef.current = { marker, element: wrapper, arrow: img };
      } else {
        robotMarkerRef.current.marker.position = robotPosition;
        robotMarkerRef.current.element.style.transform = `rotate(${heading}deg)`;
      }
    } else {
      if (robotMarkerRef.current) {
        robotMarkerRef.current.marker.map = null;
        robotMarkerRef.current = null;
      }

      const icon: google.maps.Icon = {
        url: ROBOT_ICON_URL,
        scaledSize: new google.maps.Size(40, 40),
        anchor: new google.maps.Point(20, 20)
      };

      if (!legacyRobotMarkerRef.current) {
        legacyRobotMarkerRef.current = new google.maps.Marker({
          position: robotPosition,
          map: mapInstanceRef.current,
          title: 'LawnBerryPi',
          icon
        });
      } else {
        legacyRobotMarkerRef.current.setPosition(robotPosition);
        legacyRobotMarkerRef.current.setIcon(icon);
      }
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
      const config = mapService.getConfig();
      if (config.mapId) {
        (mapOptions as google.maps.MapOptions & { mapId?: string }).mapId = config.mapId;
      }

      const map = new google.maps.Map(mapRef.current, mapOptions);

      mapInstanceRef.current = map;

      await ensureMarkerLibrary();

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
  }, [getInitialMapOptions, isOffline, onError, ensureMarkerLibrary, initializeCustomControls, setupMapEventListeners]);

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

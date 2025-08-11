import React, { useRef, useEffect, useState, useCallback } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Popup, Polyline } from 'react-leaflet';
import L from 'leaflet';
import { MapError, MapUsageLevel, MapProvider } from '../../types';
import { mapService } from '../../services/mapService';

// Fix for default markers in Leaflet
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

interface LeafletMapComponentProps {
  center: { lat: number; lng: number };
  zoom: number;
  usageLevel: MapUsageLevel;
  isOffline: boolean;
  onError: (error: MapError) => void;
  robotPosition?: { lat: number; lng: number };
  robotPath?: Array<{ lat: number; lng: number }>;
  boundaries?: Array<{ id: string; name: string; coordinates: Array<{ lat: number; lng: number }> }>;
  noGoZones?: Array<{ id: string; name: string; coordinates: Array<{ lat: number; lng: number }> }>;
  homeLocation?: { lat: number; lng: number };
  isDrawingMode?: boolean;
  drawingType?: 'boundary' | 'no-go' | 'home';
  onBoundaryComplete?: (coordinates: Array<{ lat: number; lng: number }>) => void;
  onNoGoZoneComplete?: (coordinates: Array<{ lat: number; lng: number }>) => void;
  onHomeLocationSet?: (coordinate: { lat: number; lng: number }) => void;
  style?: React.CSSProperties;
  children?: React.ReactNode;
  onMapReady?: (map: L.Map) => void;
}

// Component to handle map updates
const MapUpdater: React.FC<{
  center: { lat: number; lng: number };
  zoom: number;
}> = ({ center, zoom }) => {
  const map = useMap();
  
  useEffect(() => {
    map.setView([center.lat, center.lng], zoom);
  }, [map, center, zoom]);

  return null;
};

// Component to handle offline overlay
const OfflineOverlay: React.FC<{ isOffline: boolean }> = ({ isOffline }) => {
  const map = useMap();

  useEffect(() => {
    if (!isOffline) return;

    const offlineControl = new L.Control({ position: 'topright' });
    offlineControl.onAdd = () => {
      const div = L.DomUtil.create('div', 'offline-indicator');
      div.innerHTML = `
        <div style="
          background: rgba(0,0,0,0.8);
          color: white;
          padding: 8px 12px;
          border-radius: 4px;
          font-size: 12px;
          font-family: Arial, sans-serif;
        ">
          Offline Mode - Cached Tiles
        </div>
      `;
      return div;
    };

    offlineControl.addTo(map);

    return () => {
      offlineControl.remove();
    };
  }, [map, isOffline]);

  return null;
};

const LeafletMapComponent: React.FC<LeafletMapComponentProps> = ({
  center,
  zoom,
  usageLevel,
  isOffline,
  onError,
  robotPosition,
  robotPath,
  boundaries = [],
  noGoZones = [],
  homeLocation,
  isDrawingMode = false,
  drawingType = 'boundary',
  onBoundaryComplete,
  onNoGoZoneComplete,
  onHomeLocationSet,
  style,
  children
  , onMapReady
}) => {
  const [tileLayer, setTileLayer] = useState<string>('');
  const mapRef = useRef<L.Map | null>(null);

  const getTileLayerUrl = useCallback(() => {
    const usageSettings = mapService.getUsageLevelSettings(usageLevel);
    
    // Different tile servers based on usage level and offline capability
    if (isOffline) {
      // Use cached tiles or minimal tile server for offline
      return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    }

    switch (usageSettings.tileQuality) {
      case 'high':
        return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
      case 'medium':
        return 'https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png';
      case 'low':
        return 'https://tiles.wmflabs.org/bw-mapnik/{z}/{x}/{y}.png';
      default:
        return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    }
  }, [usageLevel, isOffline]);

  const getTileLayerOptions = useCallback(() => {
    const usageSettings = mapService.getUsageLevelSettings(usageLevel);
    
    return {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: usageSettings.enableAllFeatures ? 19 : 16,
      tileSize: 256,
      zoomOffset: 0,
      // Enable tile caching
      crossOrigin: true,
      // Performance optimizations
      updateWhenIdle: usageLevel === 'low',
      updateWhenZooming: usageLevel === 'high',
      keepBuffer: usageSettings.cacheSize
    };
  }, [usageLevel]);

  useEffect(() => {
    setTileLayer(getTileLayerUrl());
  }, [getTileLayerUrl]);

  // Basic drawing implementation (simplified vs leaflet-draw) using click sequence
  const drawingPointsRef = useRef<Array<{ lat: number; lng: number }>>([]);
  const clickHandlerRef = useRef<((e: L.LeafletMouseEvent) => void) | null>(null);
  const dblClickHandlerRef = useRef<((e: L.LeafletMouseEvent) => void) | null>(null);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    // Clean previous handlers
    if (clickHandlerRef.current) {
      map.off('click', clickHandlerRef.current);
      clickHandlerRef.current = null;
    }
    if (dblClickHandlerRef.current) {
      map.off('dblclick', dblClickHandlerRef.current);
      dblClickHandlerRef.current = null;
    }
    drawingPointsRef.current = [];

    if (!isDrawingMode) return;

    if (drawingType === 'home') {
      clickHandlerRef.current = (e: L.LeafletMouseEvent) => {
        onHomeLocationSet && onHomeLocationSet({ lat: e.latlng.lat, lng: e.latlng.lng });
      };
      map.on('click', clickHandlerRef.current);
      return;
    }

    clickHandlerRef.current = (e: L.LeafletMouseEvent) => {
      drawingPointsRef.current.push({ lat: e.latlng.lat, lng: e.latlng.lng });
      // Add a temporary marker for feedback
      L.circleMarker(e.latlng, { radius: 4, color: drawingType === 'no-go' ? '#f44336' : '#4caf50' }).addTo(map);
    };

    dblClickHandlerRef.current = () => {
      if (drawingPointsRef.current.length >= 3) {
        const pts = [...drawingPointsRef.current];
        if (drawingType === 'no-go') {
          onNoGoZoneComplete && onNoGoZoneComplete(pts);
        } else {
          onBoundaryComplete && onBoundaryComplete(pts);
        }
      }
      drawingPointsRef.current = [];
    };

    map.on('click', clickHandlerRef.current);
    map.on('dblclick', dblClickHandlerRef.current);

    return () => {
      if (clickHandlerRef.current) map.off('click', clickHandlerRef.current);
      if (dblClickHandlerRef.current) map.off('dblclick', dblClickHandlerRef.current);
    };
  }, [isDrawingMode, drawingType, onBoundaryComplete, onNoGoZoneComplete, onHomeLocationSet]);

  const handleMapCreated = useCallback((map: L.Map) => {
    mapRef.current = map;

    // Add custom controls for better UX
    const customControl = new L.Control({ position: 'topright' });
    customControl.onAdd = () => {
      const div = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
      div.innerHTML = `
        <div style="
          background: white;
          padding: 8px;
          border-radius: 4px;
          box-shadow: 0 1px 5px rgba(0,0,0,0.2);
          font-size: 12px;
          font-family: Arial, sans-serif;
          color: #4caf50;
          font-weight: bold;
        ">
          LawnBerry Maps
        </div>
      `;
      return div;
    };
    customControl.addTo(map);

    // Handle tile loading errors
    map.on('tileerror', (e: any) => {
      console.warn('Tile loading error:', e);
      if (!isOffline) {
        const networkError = mapService.createMapError(
          'network_error',
          'Failed to load map tiles. Check your internet connection.',
          'openstreetmap' as MapProvider,
          false
        );
        onError(networkError);
      }
    });

    // Add LawnBerryPi custom styling
    const style = document.createElement('style');
    style.textContent = `
      .leaflet-container {
        background: transparent !important;
      }
      .leaflet-control-container .leaflet-top .leaflet-control {
        margin-top: 60px;
      }
      .leaflet-bar {
        border: 2px solid #4caf50 !important;
      }
      .leaflet-control-zoom a {
        color: #4caf50 !important;
        border-bottom: 1px solid #4caf50 !important;
      }
      .leaflet-control-zoom a:hover {
        background: #e8f5e8 !important;
      }
      .leaflet-tile-pane {
        filter: brightness(1.05) contrast(1.1);
      }
    `;
    document.head.appendChild(style);

    onMapReady?.(map);
  }, [isOffline, onError, onMapReady]);

  const handleTileLayerError = useCallback(() => {
    const tileError = mapService.createMapError(
      'network_error',
      'Unable to load map tiles. Operating in offline mode.',
      'openstreetmap' as MapProvider,
      false
    );
    onError(tileError);
  }, [onError]);

  return (
    <div style={{ width: '100%', height: '100%', ...style }}>
      <MapContainer
        center={[center.lat, center.lng]}
        zoom={zoom}
        style={{ width: '100%', height: '100%' }}
        whenReady={() => {
          // react-leaflet passes an event-less ready callback; get map via ref after mount
          if (mapRef.current) handleMapCreated(mapRef.current);
        }}
        zoomControl={true}
        attributionControl={true}
        ref={(instance: any) => {
          if (instance && instance.target) {
            mapRef.current = instance.target as L.Map;
          } else if (instance) {
            mapRef.current = instance as unknown as L.Map;
          }
        }}
      >
        <TileLayer
          url={tileLayer}
          {...getTileLayerOptions()}
          eventHandlers={{
            tileerror: handleTileLayerError,
          }}
        />
        
        <MapUpdater center={center} zoom={zoom} />
        <OfflineOverlay isOffline={isOffline} />
      
        {robotPosition && (
          <Marker 
            position={[robotPosition.lat, robotPosition.lng]}
            icon={L.divIcon({
              className: 'robot-heading-icon',
              html: `<div style="transform: rotate(${(robotPosition as any).heading || 0}deg); width:18px;height:18px;display:flex;align-items:center;justify-content:center;">
                <svg width='18' height='18' viewBox='0 0 24 24' style='filter: drop-shadow(0 0 2px rgba(0,0,0,0.4));'>
                  <polygon points='12,2 19,22 12,17 5,22' fill='#ff9800' stroke='white' stroke-width='1.5' />
                </svg>
              </div>`
            })}
          >
            <Popup>
              LawnBerry Robot<br/>Lat: {robotPosition.lat.toFixed(5)}, Lng: {robotPosition.lng.toFixed(5)}
            </Popup>
          </Marker>
        )}

        {homeLocation && (
          <Marker position={[homeLocation.lat, homeLocation.lng]}> 
            <Popup>Home Location</Popup>
          </Marker>
        )}

        {boundaries.map(b => (
          <Polyline
            key={b.id}
            positions={b.coordinates.map(c => [c.lat, c.lng])}
            pathOptions={{ color: '#4caf50' }}
          />
        ))}

        {noGoZones.map(z => (
          <Polyline
            key={z.id}
            positions={z.coordinates.map(c => [c.lat, c.lng])}
            pathOptions={{ color: '#f44336' }}
          />
        ))}

        {robotPath && robotPath.length > 0 && (
          <Polyline
            positions={robotPath.map(p => [p.lat, p.lng])}
            color="blue"
          />
        )}
      
        {children}
      </MapContainer>
    </div>
  );
};

export default LeafletMapComponent;

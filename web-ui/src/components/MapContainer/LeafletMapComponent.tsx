import React, { useRef, useEffect, useState, useCallback } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Popup } from 'react-leaflet';
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
  style?: React.CSSProperties;
  children?: React.ReactNode;
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
  style,
  children
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
          'openstreetmap',
          false
        );
        onError(networkError);
      }
    });

    // Add LawnBerryPi custom styling
    const style = document.createElement('style');
    style.textContent = `
      .leaflet-container {
        background: #e8f5e8 !important;
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
    `;
    document.head.appendChild(style);

  }, [isOffline, onError]);

  const handleTileLayerError = useCallback(() => {
    const tileError = mapService.createMapError(
      'network_error',
      'Unable to load map tiles. Operating in offline mode.',
      'openstreetmap',
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
        whenReady={() => handleMapCreated}
        zoomControl={true}
        attributionControl={true}
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
        <Marker position={[robotPosition.lat, robotPosition.lng]}>
          <Popup>LawnBerry Robot</Popup>
        </Marker>
      )}
      
      {children}
      </MapContainer>
    </div>
  );
};

export default LeafletMapComponent;

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { MapError, MapUsageLevel } from '../../types';
import { mapService } from '../../services/mapService';

interface GoogleMapComponentProps {
  center: { lat: number; lng: number };
  zoom: number;
  usageLevel: MapUsageLevel;
  isOffline: boolean;
  onError: (error: MapError) => void;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

const GoogleMapComponent: React.FC<GoogleMapComponentProps> = ({
  center,
  zoom,
  usageLevel,
  isOffline,
  onError,
  style,
  children
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<google.maps.Map | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  const createCustomMapStyles = useCallback((): google.maps.MapTypeStyle[] => {
    // LawnBerryPi branded map styles
    return [
      {
        featureType: 'landscape' as google.maps.MapTypeStyleFeatureType,
        elementType: 'geometry.fill' as google.maps.MapTypeStyleElementType,
        stylers: [{ color: '#e8f5e8' }] // Light green for grass areas
      },
      {
        featureType: 'poi.park' as google.maps.MapTypeStyleFeatureType,
        elementType: 'geometry.fill' as google.maps.MapTypeStyleElementType,
        stylers: [{ color: '#c8e6c9' }] // Slightly darker green for parks
      },
      {
        featureType: 'water' as google.maps.MapTypeStyleFeatureType,
        elementType: 'geometry.fill' as google.maps.MapTypeStyleElementType,
        stylers: [{ color: '#81c784' }] // LawnBerry theme green for water
      },
      {
        featureType: 'road' as google.maps.MapTypeStyleFeatureType,
        elementType: 'geometry.stroke' as google.maps.MapTypeStyleElementType,
        stylers: [{ color: '#4caf50' }] // Green road borders
      }
    ];
  }, []);

  const getMapOptions = useCallback((): google.maps.MapOptions => {
    const usageSettings = mapService.getUsageLevelSettings(usageLevel);
    
    return {
      center,
      zoom,
      styles: createCustomMapStyles(),
      mapTypeControl: true,
      mapTypeControlOptions: {
        style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
        position: google.maps.ControlPosition.TOP_CENTER,
        mapTypeIds: [
          google.maps.MapTypeId.ROADMAP,
          google.maps.MapTypeId.SATELLITE,
          google.maps.MapTypeId.HYBRID,
          google.maps.MapTypeId.TERRAIN
        ]
      },
      zoomControl: true,
      zoomControlOptions: {
        position: google.maps.ControlPosition.RIGHT_CENTER
      },
      streetViewControl: false,
      fullscreenControl: true,
      fullscreenControlOptions: {
        position: google.maps.ControlPosition.RIGHT_TOP
      },
      gestureHandling: 'cooperative',
      // Performance optimizations based on usage level
      clickableIcons: usageSettings.enableAllFeatures,
      disableDefaultUI: !usageSettings.enableAllFeatures,
      backgroundColor: '#e8f5e8'
    };
  }, [center, zoom, usageLevel, createCustomMapStyles]);

  const initializeMap = useCallback(async () => {
    if (!mapRef.current || mapInstanceRef.current) return;

    try {
      // Ensure Google Maps is loaded
      if (!window.google || !window.google.maps) {
        throw new Error('Google Maps API not loaded');
      }

      const mapOptions = getMapOptions();
      const map = new google.maps.Map(mapRef.current, mapOptions);
      
      mapInstanceRef.current = map;
      setIsInitialized(true);

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
        'google',
        true
      );
      onError(mapError);
    }
  }, [getMapOptions, isOffline, onError]);

  // Initialize map on mount
  useEffect(() => {
    initializeMap();
  }, [initializeMap]);

  // Update map center and zoom when props change
  useEffect(() => {
    if (mapInstanceRef.current && isInitialized) {
      mapInstanceRef.current.setCenter(center);
      mapInstanceRef.current.setZoom(zoom);
    }
  }, [center, zoom, isInitialized]);

  // Update map options when usage level changes
  useEffect(() => {
    if (mapInstanceRef.current && isInitialized) {
      const newOptions = getMapOptions();
      mapInstanceRef.current.setOptions(newOptions);
    }
  }, [usageLevel, getMapOptions, isInitialized]);

  // Handle quota exceeded errors
  useEffect(() => {
    const handleQuotaExceeded = () => {
      const quotaError = mapService.createMapError(
        'quota_exceeded',
        'Google Maps API quota exceeded. Switching to OpenStreetMap.',
        'google',
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

  return (
    <div
      ref={mapRef}
      style={{
        width: '100%',
        height: '100%',
        ...style
      }}
    >
      {children}
    </div>
  );
};

export default GoogleMapComponent;

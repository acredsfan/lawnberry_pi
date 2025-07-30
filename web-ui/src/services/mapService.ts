import { Loader } from '@googlemaps/js-api-loader';
import { MapProvider, MapConfig, MapError, MapUsageLevel } from '../types';

export class MapService {
  private static instance: MapService;
  private googleMapsLoader: Loader | null = null;
  private leafletLoaded = false;
  private currentProvider: MapProvider = 'google';
  private config: MapConfig;

  private constructor() {
    this.config = {
      provider: 'google',
      usageLevel: 'medium',
      apiKey: (import.meta.env as any).REACT_APP_GOOGLE_MAPS_API_KEY,
      defaultCenter: { lat: 40.7128, lng: -74.0060 },
      defaultZoom: 15,
      enableCaching: true,
      offlineMode: false
    };
  }

  public static getInstance(): MapService {
    if (!MapService.instance) {
      MapService.instance = new MapService();
    }
    return MapService.instance;
  }

  public async initializeProvider(preferredProvider?: MapProvider): Promise<MapProvider> {
    const provider = preferredProvider || this.config.provider;
    
    try {
      if (provider === 'google' && this.config.apiKey) {
        await this.loadGoogleMaps();
        this.currentProvider = 'google';
        return 'google';
      } else {
        await this.loadLeaflet();
        this.currentProvider = 'openstreetmap';
        return 'openstreetmap';
      }
    } catch (error) {
      console.warn(`Failed to load ${provider}, falling back to alternative:`, error);
      
      // Fallback logic
      if (provider === 'google') {
        await this.loadLeaflet();
        this.currentProvider = 'openstreetmap';
        return 'openstreetmap';
      } else {
        throw new Error('No map provider available');
      }
    }
  }

  private async loadGoogleMaps(): Promise<void> {
    if (!this.config.apiKey) {
      throw new Error('Google Maps API key not configured');
    }

    if (!this.googleMapsLoader) {
      this.googleMapsLoader = new Loader({
        apiKey: this.config.apiKey,
        version: 'weekly',
        libraries: ['places', 'drawing', 'geometry'],
        language: 'en',
        region: 'US'
      });
    }

    await this.googleMapsLoader.load();
  }

  private async loadLeaflet(): Promise<void> {
    if (this.leafletLoaded) return;

    // Dynamically import Leaflet CSS
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(link);

    // Leaflet is already available via npm package
    this.leafletLoaded = true;
  }

  public getCurrentProvider(): MapProvider {
    return this.currentProvider;
  }

  public getConfig(): MapConfig {
    return { ...this.config };
  }

  public updateConfig(updates: Partial<MapConfig>): void {
    this.config = { ...this.config, ...updates };
  }

  public getUsageLevelSettings(level: MapUsageLevel): {
    refreshRate: number;
    tileQuality: string;
    enableAllFeatures: boolean;
    cacheSize: number;
  } {
    switch (level) {
      case 'high':
        return {
          refreshRate: 1000, // 1 second
          tileQuality: 'high',
          enableAllFeatures: true,
          cacheSize: 100
        };
      case 'medium':
        return {
          refreshRate: 5000, // 5 seconds
          tileQuality: 'medium',
          enableAllFeatures: true,
          cacheSize: 50
        };
      case 'low':
        return {
          refreshRate: 10000, // 10 seconds
          tileQuality: 'low',
          enableAllFeatures: false,
          cacheSize: 20
        };
      default:
        return this.getUsageLevelSettings('medium');
    }
  }

  public createMapError(
    type: MapError['type'],
    message: string,
    provider: MapProvider,
    canFallback: boolean = true
  ): MapError {
    return { type, message, provider, canFallback };
  }

  public async testApiKey(): Promise<boolean> {
    if (!this.config.apiKey) return false;
    
    try {
      await this.loadGoogleMaps();
      return true;
    } catch (error) {
      return false;
    }
  }
}

export const mapService = MapService.getInstance();

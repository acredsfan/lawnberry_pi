/// <reference types="vite/client" />

interface ImportMetaEnv {
  // API Configuration
  readonly VITE_API_URL: string
  readonly VITE_WEB_API_PORT: string
  
  // Google Maps Configuration
  readonly REACT_APP_GOOGLE_MAPS_API_KEY: string
  readonly REACT_APP_GOOGLE_MAPS_USAGE_LEVEL: 'low' | 'medium' | 'high'
  
  // Authentication
  readonly VITE_JWT_SECRET_KEY: string
  readonly VITE_ADMIN_PASSWORD: string
  
  // External Services
  readonly VITE_OPENWEATHER_API_KEY: string
  readonly VITE_LAWNBERRY_FLEET_API_KEY: string
  
  // Database Configuration
  readonly VITE_REDIS_PASSWORD: string
  readonly VITE_REDIS_PORT: string
  
  // MQTT Configuration
  readonly VITE_MQTT_USERNAME: string
  readonly VITE_MQTT_PASSWORD: string
  readonly VITE_MQTT_PORT: string
  
  // Location Configuration
  readonly VITE_LAT: string
  readonly VITE_LON: string
  
  // System Configuration
  readonly VITE_WEATHER_CACHE_DURATION: string
  readonly VITE_TEMP_MIN: string
  readonly VITE_TEMP_MAX: string
  readonly VITE_WIND_MAX: string
  
  // API Rate Limits
  readonly VITE_OPENWEATHER_CALLS_PER_HOUR: string
  readonly VITE_OPENWEATHER_CALLS_PER_DAY: string
  
  // Node Environment
  readonly NODE_ENV: 'development' | 'production' | 'test'
  readonly DEV: boolean
  readonly PROD: boolean
  readonly SSR: boolean
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

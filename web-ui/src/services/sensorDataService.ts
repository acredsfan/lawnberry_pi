/**
 * Real-time sensor data service
 * Provides real sensor data from WebSocket connections to hardware sensors
 */

export interface SensorData {
  gps: {
    latitude: number;
    longitude: number;
    altitude: number;
    accuracy: number;
    satellites: number;
    timestamp: string;
  };
  imu: {
    orientation: { roll: number; pitch: number; yaw: number };
    acceleration: { x: number; y: number; z: number };
    gyroscope: { x: number; y: number; z: number };
    temperature: number;
    timestamp: string;
  };
  tof: {
    left_distance: number;
    right_distance: number;
    timestamp: string;
  };
  environmental: {
    temperature: number;
    humidity: number;
    pressure: number;
    rain_detected: boolean;
    timestamp: string;
  };
  power: {
    battery_voltage: number;
    battery_current: number;
    battery_level: number;
    solar_voltage: number;
    solar_current: number;
    charging: boolean;
    timestamp: string;
  };
}

import webSocketService from './websocket';

class SensorDataService {
  private listeners: ((data: SensorData) => void)[] = [];
  private currentData: SensorData;
  private unsubscribeFunctions: (() => void)[] = [];
  private started = false;
  
  constructor() {
    // Initialize with default/empty values until real data arrives
    const now = new Date().toISOString();
    this.currentData = {
      gps: {
        latitude: 0,
        longitude: 0,
        altitude: 0,
        accuracy: 0,
        satellites: 0,
        timestamp: now
      },
      imu: {
        orientation: { roll: 0, pitch: 0, yaw: 0 },
        acceleration: { x: 0, y: 0, z: 0 },
        gyroscope: { x: 0, y: 0, z: 0 },
        temperature: 0,
        timestamp: now
      },
      tof: {
        left_distance: 0,
        right_distance: 0,
        timestamp: now
      },
      environmental: {
        temperature: 0,
        humidity: 0,
        pressure: 0,
        rain_detected: false,
        timestamp: now
      },
      power: {
        battery_voltage: 0,
        battery_current: 0,
        battery_level: 0,
        solar_voltage: 0,
        solar_current: 0,
        charging: false,
        timestamp: now
      }
    };
    
    // Defer WebSocket handler registration until start() so we fully control lifecycle
  }
  
  private setupWebSocketHandlers(): void {
    // Avoid duplicate handler registration on repeated start() calls
    if (this.unsubscribeFunctions.length > 0) return;
    // GPS data handler
    const gpsHandler = (data: any) => {
      this.currentData.gps = {
        latitude: data.latitude || 0,
        longitude: data.longitude || 0,
        altitude: data.altitude || 0,
        accuracy: data.accuracy || 0,
        satellites: data.satellites || 0,
        timestamp: data.timestamp || new Date().toISOString()
      };
      this.notifyListeners();
    };
    
    // IMU data handler
    const imuHandler = (data: any) => {
      this.currentData.imu = {
        orientation: {
          roll: data.orientation?.roll || 0,
          pitch: data.orientation?.pitch || 0,
          yaw: data.orientation?.yaw || 0
        },
        acceleration: {
          x: data.acceleration?.x || 0,
          y: data.acceleration?.y || 0,
          z: data.acceleration?.z || 0
        },
        gyroscope: {
          x: data.gyroscope?.x || 0,
          y: data.gyroscope?.y || 0,
          z: data.gyroscope?.z || 0
        },
        temperature: data.temperature || 0,
        timestamp: data.timestamp || new Date().toISOString()
      };
      this.notifyListeners();
    };
    
    // TOF sensor data handler
    const tofHandler = (data: any) => {
      this.currentData.tof = {
        left_distance: data.left_distance || 0,
        right_distance: data.right_distance || 0,
        timestamp: data.timestamp || new Date().toISOString()
      };
      this.notifyListeners();
    };
    
    // Environmental sensor data handler
    const environmentalHandler = (data: any) => {
      this.currentData.environmental = {
        temperature: data.temperature || 0,
        humidity: data.humidity || 0,
        pressure: data.pressure || 0,
        rain_detected: data.rain_detected || false,
        timestamp: data.timestamp || new Date().toISOString()
      };
      this.notifyListeners();
    };
    
    // Power data handler
    const powerHandler = (data: any) => {
      this.currentData.power = {
        battery_voltage: data.battery_voltage || 0,
        battery_current: data.battery_current || 0,
        battery_level: data.battery_level || 0,
        solar_voltage: data.solar_voltage || 0,
        solar_current: data.solar_current || 0,
        charging: data.charging || false,
        timestamp: data.timestamp || new Date().toISOString()
      };
      this.notifyListeners();
    };
    
    // Register handlers with WebSocket service
    webSocketService.on('sensors/gps/data', gpsHandler);
    webSocketService.on('sensors/imu/data', imuHandler);
    webSocketService.on('sensors/tof/data', tofHandler);
    webSocketService.on('sensors/environmental/data', environmentalHandler);
    webSocketService.on('power/battery', powerHandler);
    
    // Store unsubscribe functions
    this.unsubscribeFunctions = [
      () => webSocketService.off('sensors/gps/data', gpsHandler),
      () => webSocketService.off('sensors/imu/data', imuHandler),
      () => webSocketService.off('sensors/tof/data', tofHandler),
      () => webSocketService.off('sensors/environmental/data', environmentalHandler),
      () => webSocketService.off('power/battery', powerHandler)
    ];
  }
  
  private notifyListeners(): void {
    this.listeners.forEach(listener => {
      try {
        listener(this.currentData);
      } catch (error) {
        console.error('Error in sensor data listener:', error);
      }
    });
  }

  public start(): void {
  if (this.started) return;
  this.started = true;
  // Register handlers (idempotent)
  this.setupWebSocketHandlers();
    // Subscribe to sensor topics when starting
    webSocketService.subscribe([
      'sensors/gps/data',
      'sensors/imu/data', 
      'sensors/tof/data',
      'sensors/environmental/data',
      'power/battery'
    ]);
    
    console.log('Sensor data service started with WebSocket subscriptions');
  }

  public stop(): void {
  this.started = false;
    // Unsubscribe from all sensor topics when stopping
    webSocketService.unsubscribe([
      'sensors/gps/data',
      'sensors/imu/data',
      'sensors/tof/data', 
      'sensors/environmental/data',
      'power/battery'
    ]);
    
    // Clear all unsubscribe functions
    this.unsubscribeFunctions.forEach(unsubscribe => unsubscribe());
    this.unsubscribeFunctions = [];
    
    console.log('Sensor data service stopped and unsubscribed from WebSocket topics');
  }

  public subscribe(listener: (data: SensorData) => void): () => void {
    this.listeners.push(listener);
    
    // Send current data immediately
    setTimeout(() => {
      try {
        listener(this.currentData);
      } catch (error) {
        console.error('Error in sensor data listener:', error);
      }
    }, 0);
    
    // Return unsubscribe function
    return () => {
      const index = this.listeners.indexOf(listener);
      if (index > -1) {
        this.listeners.splice(index, 1);
      }
    };
  }

  public getCurrentData(): SensorData {
    return { ...this.currentData };
  }
}

// Export singleton instance
export const sensorDataService = new SensorDataService();

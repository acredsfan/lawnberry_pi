/**
 * Units System for LawnBerryPi WebUI
 * Handles conversion between metric/imperial units and temperature scales
 */

export type UnitSystem = 'metric' | 'imperial';
export type TemperatureUnit = 'celsius' | 'fahrenheit';

export interface UnitPreferences {
  system: UnitSystem;
  temperature: TemperatureUnit;
}

export interface ConvertedValue {
  value: number;
  unit: string;
  formatted: string;
}

export class UnitsService {
  private preferences: UnitPreferences = {
    system: 'metric',
    temperature: 'celsius'
  };

  private listeners: ((preferences: UnitPreferences) => void)[] = [];

  constructor() {
    // Load preferences from localStorage
    this.loadPreferences();
  }

  private loadPreferences(): void {
    try {
      const stored = localStorage.getItem('lawnberry_unit_preferences');
      if (stored) {
        const parsed = JSON.parse(stored);
        this.preferences = {
          system: parsed.system || 'metric',
          temperature: parsed.temperature || 'celsius'
        };
      }
    } catch (error) {
      console.warn('Failed to load unit preferences:', error);
    }
  }

  private savePreferences(): void {
    try {
      localStorage.setItem('lawnberry_unit_preferences', JSON.stringify(this.preferences));
    } catch (error) {
      console.warn('Failed to save unit preferences:', error);
    }
  }

  private notifyListeners(): void {
    this.listeners.forEach(listener => {
      try {
        listener(this.preferences);
      } catch (error) {
        console.error('Error in units preference listener:', error);
      }
    });
  }

  // Public API
  public getPreferences(): UnitPreferences {
    return { ...this.preferences };
  }

  public setSystem(system: UnitSystem): void {
    this.preferences.system = system;
    this.savePreferences();
    this.notifyListeners();
  }

  public setTemperature(temperature: TemperatureUnit): void {
    this.preferences.temperature = temperature;
    this.savePreferences();
    this.notifyListeners();
  }

  public subscribe(listener: (preferences: UnitPreferences) => void): () => void {
    this.listeners.push(listener);
    
    // Send current preferences immediately
    setTimeout(() => {
      try {
        listener(this.preferences);
      } catch (error) {
        console.error('Error in units preference listener:', error);
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

  // Temperature Conversions
  public convertTemperature(celsius: number): ConvertedValue {
    if (this.preferences.temperature === 'fahrenheit') {
      const fahrenheit = (celsius * 9/5) + 32;
      return {
        value: fahrenheit,
        unit: '°F',
        formatted: `${fahrenheit.toFixed(1)}°F`
      };
    } else {
      return {
        value: celsius,
        unit: '°C',
        formatted: `${celsius.toFixed(1)}°C`
      };
    }
  }

  // Distance Conversions
  public convertDistance(meters: number): ConvertedValue {
    if (this.preferences.system === 'imperial') {
      if (meters < 0.9144) { // Less than 1 yard, show in inches
        const inches = meters * 39.3701;
        return {
          value: inches,
          unit: 'in',
          formatted: `${inches.toFixed(1)} in`
        };
      } else if (meters < 1609.34) { // Less than 1 mile, show in feet/yards
        const feet = meters * 3.28084;
        if (feet < 100) {
          return {
            value: feet,
            unit: 'ft',
            formatted: `${feet.toFixed(1)} ft`
          };
        } else {
          const yards = feet / 3;
          return {
            value: yards,
            unit: 'yd',
            formatted: `${yards.toFixed(1)} yd`
          };
        }
      } else { // Miles
        const miles = meters / 1609.34;
        return {
          value: miles,
          unit: 'mi',
          formatted: `${miles.toFixed(2)} mi`
        };
      }
    } else {
      if (meters < 1) { // Less than 1 meter, show in centimeters
        const cm = meters * 100;
        return {
          value: cm,
          unit: 'cm',
          formatted: `${cm.toFixed(1)} cm`
        };
      } else if (meters < 1000) { // Less than 1 km, show in meters
        return {
          value: meters,
          unit: 'm',
          formatted: `${meters.toFixed(1)} m`
        };
      } else { // Kilometers
        const km = meters / 1000;
        return {
          value: km,
          unit: 'km',
          formatted: `${km.toFixed(2)} km`
        };
      }
    }
  }

  // Area Conversions
  public convertArea(squareMeters: number): ConvertedValue {
    if (this.preferences.system === 'imperial') {
      if (squareMeters < 4046.86) { // Less than 1 acre, show in square feet
        const sqft = squareMeters * 10.7639;
        return {
          value: sqft,
          unit: 'sq ft',
          formatted: `${sqft.toFixed(0)} sq ft`
        };
      } else { // Acres
        const acres = squareMeters / 4046.86;
        return {
          value: acres,
          unit: 'acres',
          formatted: `${acres.toFixed(2)} acres`
        };
      }
    } else {
      if (squareMeters < 10000) { // Less than 1 hectare, show in square meters
        return {
          value: squareMeters,
          unit: 'm²',
          formatted: `${squareMeters.toFixed(0)} m²`
        };
      } else { // Hectares
        const hectares = squareMeters / 10000;
        return {
          value: hectares,
          unit: 'ha',
          formatted: `${hectares.toFixed(2)} ha`
        };
      }
    }
  }

  // Speed Conversions
  public convertSpeed(metersPerSecond: number): ConvertedValue {
    if (this.preferences.system === 'imperial') {
      const mph = metersPerSecond * 2.23694;
      return {
        value: mph,
        unit: 'mph',
        formatted: `${mph.toFixed(1)} mph`
      };
    } else {
      const kmh = metersPerSecond * 3.6;
      return {
        value: kmh,
        unit: 'km/h',
        formatted: `${kmh.toFixed(1)} km/h`
      };
    }
  }

  // Power Conversions (for battery and solar)
  public convertPower(watts: number): ConvertedValue {
    // Power typically stays in watts regardless of system
    if (watts < 1000) {
      return {
        value: watts,
        unit: 'W',
        formatted: `${watts.toFixed(1)} W`
      };
    } else {
      const kw = watts / 1000;
      return {
        value: kw,
        unit: 'kW',
        formatted: `${kw.toFixed(2)} kW`
      };
    }
  }

  // Pressure Conversions
  public convertPressure(pascals: number): ConvertedValue {
    if (this.preferences.system === 'imperial') {
      const psi = pascals * 0.000145038;
      return {
        value: psi,
        unit: 'psi',
        formatted: `${psi.toFixed(2)} psi`
      };
    } else {
      const hPa = pascals / 100; // hectopascals (millibars)
      return {
        value: hPa,
        unit: 'hPa',
        formatted: `${hPa.toFixed(1)} hPa`
      };
    }
  }

  // Voltage (stays the same regardless of system)
  public formatVoltage(volts: number): ConvertedValue {
    return {
      value: volts,
      unit: 'V',
      formatted: `${volts.toFixed(1)} V`
    };
  }

  // Current (stays the same regardless of system)
  public formatCurrent(amperes: number): ConvertedValue {
    return {
      value: amperes,
      unit: 'A',
      formatted: `${amperes.toFixed(2)} A`
    };
  }

  // Convenience methods for common formatting
  public formatTemperature(celsius: number): string {
    return this.convertTemperature(celsius).formatted;
  }

  public formatDistance(meters: number): string {
    return this.convertDistance(meters).formatted;
  }

  public formatArea(squareMeters: number): string {
    return this.convertArea(squareMeters).formatted;
  }

  public formatSpeed(metersPerSecond: number): string {
    return this.convertSpeed(metersPerSecond).formatted;
  }

  public formatPower(watts: number): string {
    return this.convertPower(watts).formatted;
  }

  public formatPressure(pascals: number): string {
    return this.convertPressure(pascals).formatted;
  }

  // Get unit labels for display
  public getDistanceUnit(): string {
    return this.preferences.system === 'imperial' ? 'ft' : 'm';
  }

  public getAreaUnit(): string {
    return this.preferences.system === 'imperial' ? 'sq ft' : 'm²';
  }

  public getTemperatureUnit(): string {
    return this.preferences.temperature === 'fahrenheit' ? '°F' : '°C';
  }

  public getSpeedUnit(): string {
    return this.preferences.system === 'imperial' ? 'mph' : 'km/h';
  }
}

// Export singleton instance
export const unitsService = new UnitsService();

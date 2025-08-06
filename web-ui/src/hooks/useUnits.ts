/**
 * useUnits Hook
 * Custom hook for easy access to units conversion and formatting
 */

import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../store/store';
import { 
  setUnitPreferences, 
  initializeUnits,
  selectUnitSystem, 
  selectTemperatureUnit,
  selectUnitPreferences 
} from '../store/slices/unitsSlice';
import { unitsService, UnitPreferences } from '../services/unitsService';

export const useUnits = () => {
  const dispatch = useDispatch();
  const unitSystem = useSelector(selectUnitSystem);
  const temperatureUnit = useSelector(selectTemperatureUnit);
  const unitPreferences = useSelector(selectUnitPreferences);

  // Initialize units from localStorage on first load
  useEffect(() => {
    const unsubscribe = unitsService.subscribe((preferences: UnitPreferences) => {
      dispatch(setUnitPreferences(preferences));
    });

    // Initialize with current preferences
    const currentPrefs = unitsService.getPreferences();
    dispatch(initializeUnits(currentPrefs));

    return unsubscribe;
  }, [dispatch]);

  // Convenience methods that automatically use current preferences
  const formatters = {
    temperature: (celsius: number) => unitsService.formatTemperature(celsius),
    distance: (meters: number) => unitsService.formatDistance(meters),
    area: (squareMeters: number) => unitsService.formatArea(squareMeters),
    speed: (metersPerSecond: number) => unitsService.formatSpeed(metersPerSecond),
    power: (watts: number) => unitsService.formatPower(watts),
    pressure: (pascals: number) => unitsService.formatPressure(pascals),
    voltage: (volts: number) => unitsService.formatVoltage(volts).formatted,
    current: (amperes: number) => unitsService.formatCurrent(amperes).formatted
  };

  const converters = {
    temperature: (celsius: number) => unitsService.convertTemperature(celsius),
    distance: (meters: number) => unitsService.convertDistance(meters),
    area: (squareMeters: number) => unitsService.convertArea(squareMeters),
    speed: (metersPerSecond: number) => unitsService.convertSpeed(metersPerSecond),
    power: (watts: number) => unitsService.convertPower(watts),
    pressure: (pascals: number) => unitsService.convertPressure(pascals)
  };

  const units = {
    distance: unitsService.getDistanceUnit(),
    area: unitsService.getAreaUnit(),
    temperature: unitsService.getTemperatureUnit(),
    speed: unitsService.getSpeedUnit()
  };

  return {
    // Current preferences
    unitSystem,
    temperatureUnit,
    unitPreferences,
    
    // Formatting functions (return strings)
    format: formatters,
    
    // Conversion functions (return ConvertedValue objects)
    convert: converters,
    
    // Unit labels
    units,
    
    // Direct access to service
    service: unitsService
  };
};

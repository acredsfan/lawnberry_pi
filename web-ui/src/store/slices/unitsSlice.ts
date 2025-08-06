/**
 * Units Redux Slice
 * Manages unit system preferences in application state
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { UnitSystem, TemperatureUnit, UnitPreferences } from '../../services/unitsService';

export interface UnitsState {
  system: UnitSystem;
  temperature: TemperatureUnit;
  isInitialized: boolean;
}

const initialState: UnitsState = {
  system: 'metric',
  temperature: 'celsius',
  isInitialized: false
};

const unitsSlice = createSlice({
  name: 'units',
  initialState,
  reducers: {
    setUnitSystem: (state, action: PayloadAction<UnitSystem>) => {
      state.system = action.payload;
    },
    setTemperatureUnit: (state, action: PayloadAction<TemperatureUnit>) => {
      state.temperature = action.payload;
    },
    setUnitPreferences: (state, action: PayloadAction<UnitPreferences>) => {
      state.system = action.payload.system;
      state.temperature = action.payload.temperature;
      state.isInitialized = true;
    },
    initializeUnits: (state, action: PayloadAction<UnitPreferences>) => {
      if (!state.isInitialized) {
        state.system = action.payload.system;
        state.temperature = action.payload.temperature;
        state.isInitialized = true;
      }
    }
  }
});

export const { setUnitSystem, setTemperatureUnit, setUnitPreferences, initializeUnits } = unitsSlice.actions;

// Selectors
export const selectUnitSystem = (state: { units: UnitsState }) => state.units.system;
export const selectTemperatureUnit = (state: { units: UnitsState }) => state.units.temperature;
export const selectUnitPreferences = (state: { units: UnitsState }): UnitPreferences => ({
  system: state.units.system,
  temperature: state.units.temperature
});
export const selectUnitsInitialized = (state: { units: UnitsState }) => state.units.isInitialized;

export default unitsSlice.reducer;

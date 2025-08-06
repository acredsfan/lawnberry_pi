/**
 * Units Settings Component
 * Allows users to switch between metric/imperial and Celsius/Fahrenheit
 */

import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Box,
  Chip,
  Divider
} from '@mui/material';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store/store';
import { setUnitSystem, setTemperatureUnit, selectUnitSystem, selectTemperatureUnit } from '../../store/slices/unitsSlice';
import { UnitSystem, TemperatureUnit, unitsService } from '../../services/unitsService';

interface UnitsSettingsProps {
  standalone?: boolean; // Whether this is a standalone component or part of settings page
}

const UnitsSettings: React.FC<UnitsSettingsProps> = ({ standalone = false }) => {
  const dispatch = useDispatch();
  const currentSystem = useSelector(selectUnitSystem);
  const currentTemperature = useSelector(selectTemperatureUnit);

  const handleSystemChange = (system: UnitSystem) => {
    dispatch(setUnitSystem(system));
    unitsService.setSystem(system);
  };

  const handleTemperatureChange = (temperature: TemperatureUnit) => {
    dispatch(setTemperatureUnit(temperature));
    unitsService.setTemperature(temperature);
  };

  // Example conversions for preview
  const exampleDistance = 100; // 100 meters
  const exampleArea = 1000; // 1000 square meters
  const exampleTemp = 25; // 25°C
  const exampleSpeed = 5; // 5 m/s

  const distanceExample = unitsService.convertDistance(exampleDistance);
  const areaExample = unitsService.convertArea(exampleArea);
  const tempExample = unitsService.convertTemperature(exampleTemp);
  const speedExample = unitsService.convertSpeed(exampleSpeed);

  const content = (
    <>
      <Typography variant="h6" gutterBottom>
        Units & Measurements
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Choose your preferred unit system for displaying measurements throughout the application.
      </Typography>

      <Grid container spacing={3}>
        {/* Unit System Selection */}
        <Grid item xs={12} md={6}>
          <FormControl fullWidth>
            <InputLabel>Measurement System</InputLabel>
            <Select
              value={currentSystem}
              label="Measurement System"
              onChange={(e) => handleSystemChange(e.target.value as UnitSystem)}
            >
              <MenuItem value="metric">
                <Box>
                  <Typography variant="body1">Metric</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Meters, kilometers, square meters, km/h
                  </Typography>
                </Box>
              </MenuItem>
              <MenuItem value="imperial">
                <Box>
                  <Typography variant="body1">Imperial</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Feet, yards, miles, square feet, mph
                  </Typography>
                </Box>
              </MenuItem>
            </Select>
          </FormControl>
        </Grid>

        {/* Temperature Unit Selection */}
        <Grid item xs={12} md={6}>
          <FormControl fullWidth>
            <InputLabel>Temperature Scale</InputLabel>
            <Select
              value={currentTemperature}
              label="Temperature Scale"
              onChange={(e) => handleTemperatureChange(e.target.value as TemperatureUnit)}
            >
              <MenuItem value="celsius">
                <Box>
                  <Typography variant="body1">Celsius (°C)</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Water freezes at 0°C, boils at 100°C
                  </Typography>
                </Box>
              </MenuItem>
              <MenuItem value="fahrenheit">
                <Box>
                  <Typography variant="body1">Fahrenheit (°F)</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Water freezes at 32°F, boils at 212°F
                  </Typography>
                </Box>
              </MenuItem>
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      <Divider sx={{ my: 3 }} />

      {/* Preview Examples */}
      <Typography variant="subtitle2" gutterBottom>
        Preview Examples
      </Typography>
      
      <Grid container spacing={2}>
        <Grid item xs={6} sm={3}>
          <Box textAlign="center">
            <Typography variant="caption" color="text.secondary">Distance</Typography>
            <Typography variant="body2" fontWeight="medium">
              {distanceExample.formatted}
            </Typography>
          </Box>
        </Grid>
        
        <Grid item xs={6} sm={3}>
          <Box textAlign="center">
            <Typography variant="caption" color="text.secondary">Area</Typography>
            <Typography variant="body2" fontWeight="medium">
              {areaExample.formatted}
            </Typography>
          </Box>
        </Grid>
        
        <Grid item xs={6} sm={3}>
          <Box textAlign="center">
            <Typography variant="caption" color="text.secondary">Temperature</Typography>
            <Typography variant="body2" fontWeight="medium">
              {tempExample.formatted}
            </Typography>
          </Box>
        </Grid>
        
        <Grid item xs={6} sm={3}>
          <Box textAlign="center">
            <Typography variant="caption" color="text.secondary">Speed</Typography>
            <Typography variant="body2" fontWeight="medium">
              {speedExample.formatted}
            </Typography>
          </Box>
        </Grid>
      </Grid>

      <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Chip 
          label={`System: ${currentSystem}`} 
          color="primary" 
          variant="outlined" 
          size="small" 
        />
        <Chip 
          label={`Temperature: ${currentTemperature}`} 
          color="secondary" 
          variant="outlined" 
          size="small" 
        />
      </Box>
    </>
  );

  if (standalone) {
    return (
      <Card>
        <CardContent>
          {content}
        </CardContent>
      </Card>
    );
  }

  return content;
};

export default UnitsSettings;

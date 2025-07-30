import React, { useState } from 'react'
import { Box, Card, CardContent, Typography, Grid, TextField, FormControl, InputLabel, Select, MenuItem, Switch, FormControlLabel, Button, Divider, Slider, Alert } from '@mui/material'
import { Save as SaveIcon, RestoreSharp as ResetIcon } from '@mui/icons-material'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '../store/store'
import { updateUnits, updateSafety, updateOperation, updateDisplay, updateBatteryThresholds, resetToDefaults } from '../store/slices/settingsSlice'

const Settings: React.FC = () => {
  const dispatch = useDispatch()
  const settings = useSelector((state: RootState) => state.settings)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')

  const handleSave = async () => {
    setSaveStatus('saving')
    try {
      // In a real app, this would save to backend
      await new Promise(resolve => setTimeout(resolve, 1000))
      setSaveStatus('success')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (error) {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 3000)
    }
  }

  const handleReset = () => {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
      dispatch(resetToDefaults())
    }
  }

  return (
    <Box sx={{ height: '100%', overflow: 'auto' }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">Settings</Typography>
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<ResetIcon />}
            onClick={handleReset}
            color="warning"
          >
            Reset to Defaults
          </Button>
          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={handleSave}
            disabled={saveStatus === 'saving'}
          >
            {saveStatus === 'saving' ? 'Saving...' : 'Save Settings'}
          </Button>
        </Box>
      </Box>

      {saveStatus === 'success' && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Settings saved successfully!
        </Alert>
      )}

      {saveStatus === 'error' && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to save settings. Please try again.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Units Settings */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Units & Display
              </Typography>
              
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <FormControl fullWidth>
                    <InputLabel>Temperature Unit</InputLabel>
                    <Select
                      value={settings.units.temperature}
                      label="Temperature Unit"
                      onChange={(e) => dispatch(updateUnits({ 
                        temperature: e.target.value as 'celsius' | 'fahrenheit' 
                      }))}
                    >
                      <MenuItem value="celsius">Celsius (°C)</MenuItem>
                      <MenuItem value="fahrenheit">Fahrenheit (°F)</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12}>
                  <FormControl fullWidth>
                    <InputLabel>Distance Unit</InputLabel>
                    <Select
                      value={settings.units.distance}
                      label="Distance Unit"
                      onChange={(e) => dispatch(updateUnits({ 
                        distance: e.target.value as 'metric' | 'imperial' 
                      }))}
                    >
                      <MenuItem value="metric">Metric (m, km)</MenuItem>
                      <MenuItem value="imperial">Imperial (ft, mi)</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12}>
                  <FormControl fullWidth>
                    <InputLabel>Speed Unit</InputLabel>
                    <Select
                      value={settings.units.speed}
                      label="Speed Unit"
                      onChange={(e) => dispatch(updateUnits({ 
                        speed: e.target.value as 'ms' | 'kmh' | 'mph' 
                      }))}
                    >
                      <MenuItem value="ms">m/s</MenuItem>
                      <MenuItem value="kmh">km/h</MenuItem>
                      <MenuItem value="mph">mph</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>

                <Grid item xs={12}>
                  <FormControl fullWidth>
                    <InputLabel>Theme</InputLabel>
                    <Select
                      value={settings.display.theme}
                      label="Theme"
                      onChange={(e) => dispatch(updateDisplay({ 
                        theme: e.target.value as 'light' | 'dark' | 'auto' 
                      }))}
                    >
                      <MenuItem value="light">Light</MenuItem>
                      <MenuItem value="dark">Dark</MenuItem>
                      <MenuItem value="auto">Auto</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>

                <Grid item xs={12}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings.display.showAdvanced}
                        onChange={(e) => dispatch(updateDisplay({ 
                          showAdvanced: e.target.checked 
                        }))}
                      />
                    }
                    label="Show Advanced Options"
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Safety Settings */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Safety Settings
              </Typography>
              
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <Typography gutterBottom>
                    Emergency Stop Distance: {settings.safety.emergencyStopDistance}m
                  </Typography>
                  <Slider
                    value={settings.safety.emergencyStopDistance}
                    onChange={(_, value) => dispatch(updateSafety({ 
                      emergencyStopDistance: value as number 
                    }))}
                    min={0.1}
                    max={2.0}
                    step={0.1}
                    marks={[
                      { value: 0.5, label: '0.5m' },
                      { value: 1.0, label: '1.0m' },
                      { value: 1.5, label: '1.5m' }
                    ]}
                  />
                </Grid>

                <Grid item xs={12}>
                  <Typography gutterBottom>
                    Max Slope: {settings.safety.maxSlope}°
                  </Typography>
                  <Slider
                    value={settings.safety.maxSlope}
                    onChange={(_, value) => dispatch(updateSafety({ 
                      maxSlope: value as number 
                    }))}
                    min={5}
                    max={30}
                    step={1}
                    marks={[
                      { value: 10, label: '10°' },
                      { value: 15, label: '15°' },
                      { value: 20, label: '20°' }
                    ]}
                  />
                </Grid>

                <Grid item xs={12}>
                  <Typography gutterBottom>
                    Obstacle Detection Sensitivity: {(settings.safety.obstacleDetectionSensitivity * 100).toFixed(0)}%
                  </Typography>
                  <Slider
                    value={settings.safety.obstacleDetectionSensitivity}
                    onChange={(_, value) => dispatch(updateSafety({ 
                      obstacleDetectionSensitivity: value as number 
                    }))}
                    min={0.1}
                    max={1.0}
                    step={0.1}
                    marks={[
                      { value: 0.3, label: 'Low' },
                      { value: 0.6, label: 'Medium' },
                      { value: 0.9, label: 'High' }
                    ]}
                  />
                </Grid>

                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Response Time (ms)"
                    type="number"
                    value={settings.safety.responseTime}
                    onChange={(e) => dispatch(updateSafety({ 
                      responseTime: parseInt(e.target.value) 
                    }))}
                    inputProps={{ min: 50, max: 500 }}
                    helperText="Target: 100ms for emergency response"
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Operation Settings */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Operation Settings
              </Typography>
              
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Default Speed (m/s)"
                    type="number"
                    value={settings.operation.defaultSpeed}
                    onChange={(e) => dispatch(updateOperation({ 
                      defaultSpeed: parseFloat(e.target.value) 
                    }))}
                    inputProps={{ min: 0.1, max: 3.0, step: 0.1 }}
                    helperText="Recommended: 1.0 m/s for autonomous mowing"
                  />
                </Grid>

                <Grid item xs={12}>
                  <Typography variant="subtitle2" gutterBottom>
                    Battery Thresholds
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                </Grid>

                <Grid item xs={4}>
                  <TextField
                    fullWidth
                    label="Critical (%)"
                    type="number"
                    value={settings.operation.batteryThresholds.critical}
                    onChange={(e) => dispatch(updateBatteryThresholds({ 
                      critical: parseInt(e.target.value) 
                    }))}
                    inputProps={{ min: 5, max: 25 }}
                    size="small"
                  />
                </Grid>

                <Grid item xs={4}>
                  <TextField
                    fullWidth
                    label="Low (%)"
                    type="number"
                    value={settings.operation.batteryThresholds.low}
                    onChange={(e) => dispatch(updateBatteryThresholds({ 
                      low: parseInt(e.target.value) 
                    }))}
                    inputProps={{ min: 15, max: 35 }}
                    size="small"
                  />
                </Grid>

                <Grid item xs={4}>
                  <TextField
                    fullWidth
                    label="Return (%)"
                    type="number"
                    value={settings.operation.batteryThresholds.return}
                    onChange={(e) => dispatch(updateBatteryThresholds({ 
                      return: parseInt(e.target.value) 
                    }))}
                    inputProps={{ min: 25, max: 50 }}
                    size="small"
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Advanced Settings */}
        {settings.display.showAdvanced && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Advanced Settings
                </Typography>
                
                <Grid container spacing={3}>
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="Refresh Rate (ms)"
                      type="number"
                      value={settings.display.refreshRate}
                      onChange={(e) => dispatch(updateDisplay({ 
                        refreshRate: parseInt(e.target.value) 
                      }))}
                      inputProps={{ min: 100, max: 5000 }}
                      helperText="How often to update the display (lower = more responsive, higher CPU usage)"
                    />
                  </Grid>

                  <Grid item xs={12}>
                    <Typography variant="body2" color="text.secondary">
                      <strong>Note:</strong> Advanced settings can affect system performance. 
                      Only modify these if you understand their impact.
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Box>
  )
}

export default Settings

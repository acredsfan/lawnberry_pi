import React, { useEffect, useState } from 'react';
import { Card, CardContent, Typography, Box, LinearProgress, Grid, Button, Chip, Switch, Tooltip, IconButton, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Alert } from '@mui/material';
import { WbSunny, PowerSettingsNew, BatteryChargingFull, BatteryAlert, Settings } from '@mui/icons-material';
import { api } from '../../utils/api';

interface PowerStatus {
  battery_level: number;
  battery_voltage: number;
  battery_current: number;
  battery_charging: boolean;
  solar_power: number;
  shutdown_thresholds: {
    critical: number;
    warning: number;
    return_to_base: number;
  };
  mode: string;
  sunny_spot_available: boolean;
}

const PowerManagementPanel: React.FC = () => {
  const [status, setStatus] = useState<PowerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [thresholdDialogOpen, setThresholdDialogOpen] = useState(false);
  const [thresholds, setThresholds] = useState({ critical: 5, warning: 15, return_to_base: 25 });
  const [sunnySeekLoading, setSunnySeekLoading] = useState(false);
  const [mode, setMode] = useState('auto');

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const response = await api.power.getStatus();
      setStatus(response.data);
      setThresholds(response.data.shutdown_thresholds);
      setMode(response.data.mode);
      setError(null);
    } catch (err) {
      setError('Failed to fetch power status');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleThresholdSave = async () => {
    try {
      await api.power.updateShutdownThresholds(thresholds);
      setThresholdDialogOpen(false);
      fetchStatus();
    } catch (err) {
      setError('Failed to update shutdown thresholds');
    }
  };

  const handleSunnySeek = async () => {
    setSunnySeekLoading(true);
    try {
      await api.power.seekSunnySpot();
      fetchStatus();
    } catch (err) {
      setError('Failed to seek sunny spot');
    }
    setSunnySeekLoading(false);
  };

  const handleModeChange = async (newMode: string) => {
    try {
      await api.power.setMode(newMode);
      setMode(newMode);
      fetchStatus();
    } catch (err) {
      setError('Failed to change power mode');
    }
  };

  if (loading) {
    return <Card><CardContent><Typography>Loading power management...</Typography></CardContent></Card>;
  }

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <BatteryChargingFull color={status?.battery_charging ? 'success' : 'warning'} />
          <Typography variant="h6">Power Management</Typography>
          <Chip label={mode.toUpperCase()} color="info" />
          <Tooltip title="Configure Shutdown Thresholds">
            <IconButton onClick={() => setThresholdDialogOpen(true)}><Settings /></IconButton>
          </Tooltip>
        </Box>
        <Grid container spacing={2}>
          <Grid item xs={6}>
            <Typography variant="body2">Battery Level</Typography>
            <LinearProgress variant="determinate" value={status?.battery_level || 0} sx={{ height: 10, borderRadius: 5 }} />
            <Typography variant="caption">{status?.battery_level?.toFixed(1) || '0.0'}%</Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2">Solar Power</Typography>
            <Typography variant="caption">{status?.solar_power?.toFixed(2) || '0.00'} W</Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2">Voltage</Typography>
            <Typography variant="caption">{status?.battery_voltage?.toFixed(2) || '0.00'} V</Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2">Current</Typography>
            <Typography variant="caption">{status?.battery_current?.toFixed(2) || '0.00'} A</Typography>
          </Grid>
        </Grid>
        <Box mt={2} display="flex" gap={2}>
          <Button variant="contained" color="primary" onClick={() => handleModeChange('auto')} disabled={mode==='auto'}>Auto</Button>
          <Button variant="contained" color="secondary" onClick={() => handleModeChange('eco')} disabled={mode==='eco'}>Eco</Button>
          <Button variant="contained" color="warning" onClick={() => handleModeChange('performance')} disabled={mode==='performance'}>Performance</Button>
          <Button variant="contained" color="error" onClick={() => handleModeChange('emergency')} disabled={mode==='emergency'}>Emergency</Button>
        </Box>
        <Box mt={2} display="flex" gap={2}>
          <Button variant="outlined" color="success" startIcon={<WbSunny />} onClick={handleSunnySeek} disabled={!status?.sunny_spot_available || sunnySeekLoading}>
            Seek Sun
          </Button>
          <Button variant="outlined" color="error" startIcon={<PowerSettingsNew />} onClick={() => api.power.emergencyShutdown()}>Emergency Shutdown</Button>
        </Box>
        <Dialog open={thresholdDialogOpen} onClose={() => setThresholdDialogOpen(false)}>
          <DialogTitle>Configure Shutdown Thresholds</DialogTitle>
          <DialogContent>
            <TextField
              label="Critical (%)"
              type="number"
              value={thresholds.critical}
              onChange={e => setThresholds({ ...thresholds, critical: Number(e.target.value) })}
              fullWidth
              margin="dense"
            />
            <TextField
              label="Warning (%)"
              type="number"
              value={thresholds.warning}
              onChange={e => setThresholds({ ...thresholds, warning: Number(e.target.value) })}
              fullWidth
              margin="dense"
            />
            <TextField
              label="Return to Base (%)"
              type="number"
              value={thresholds.return_to_base}
              onChange={e => setThresholds({ ...thresholds, return_to_base: Number(e.target.value) })}
              fullWidth
              margin="dense"
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setThresholdDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleThresholdSave} variant="contained">Save</Button>
          </DialogActions>
        </Dialog>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </CardContent>
    </Card>
  );
};

export default PowerManagementPanel;

import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Switch,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Chip,
  LinearProgress,
  Divider,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  SelectChangeEvent
} from '@mui/material';
import {
  RadioButtonChecked,
  RadioButtonUnchecked,
  Emergency,
  Settings,
  Refresh,
  Warning,
  CheckCircle,
  Error,
  PowerSettingsNew
} from '@mui/icons-material';
import { useWebSocket } from '../hooks/useWebSocket';
import { apiClient } from '../utils/api';

interface RCStatus {
  rc_enabled: boolean;
  rc_mode: string;
  signal_lost: boolean;
  blade_enabled: boolean;
  channels: Record<number, number>;
  encoder_position: number;
  timestamp: string;
}

interface ChannelConfig {
  function: string;
  min: number;
  max: number;
  center: number;
}

const RC_MODES = [
  { value: 'emergency', label: 'Emergency Only', description: 'RC control only for emergency situations' },
  { value: 'manual', label: 'Full Manual', description: 'Complete manual control of all functions' },
  { value: 'assisted', label: 'Assisted Mode', description: 'Manual control with safety oversight' },
  { value: 'training', label: 'Training Mode', description: 'Manual control with movement recording' }
];

const CHANNEL_FUNCTIONS = [
  'steer', 'throttle', 'blade', 'speed_adj', 'emergency', 'mode_switch'
];

const RCControl: React.FC = () => {
  const [status, setStatus] = useState<RCStatus | null>(null);
  const [channels, setChannels] = useState<Record<number, ChannelConfig>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState<number>(1);
  const [selectedFunction, setSelectedFunction] = useState<string>('steer');

  const { isConnected } = useWebSocket('ws://localhost:8000/ws');

  // Fetch RC status
  const fetchStatus = async () => {
    try {
      const response = await apiClient.get('/api/v1/rc/status');
      setStatus(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch RC status');
      console.error('RC status fetch error:', err);
    }
  };

  // Fetch channel configuration
  const fetchChannels = async () => {
    try {
      const response = await apiClient.get('/api/v1/rc/channels');
      setChannels(response.data);
    } catch (err) {
      console.error('Channel config fetch error:', err);
    }
  };

  // Initial data fetch
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchStatus(), fetchChannels()]);
      setLoading(false);
    };

    loadData();
    
    // Set up polling
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Handle RC enable/disable
  const handleRCToggle = async (enabled: boolean) => {
    try {
      const endpoint = enabled ? '/api/v1/rc/enable' : '/api/v1/rc/disable';
      await apiClient.post(endpoint);
      await fetchStatus();
    } catch (err) {
      setError(`Failed to ${enabled ? 'enable' : 'disable'} RC control`);
    }
  };

  // Handle mode change
  const handleModeChange = async (event: SelectChangeEvent) => {
    const mode = event.target.value;
    try {
      await apiClient.post('/api/v1/rc/mode', { mode });
      await fetchStatus();
    } catch (err) {
      setError('Failed to change RC mode');
    }
  };

  // Handle blade control
  const handleBladeToggle = async (enabled: boolean) => {
    try {
      await apiClient.post('/api/v1/rc/blade', { enabled });
      await fetchStatus();
    } catch (err) {
      setError('Failed to control blade');
    }
  };

  // Handle emergency stop
  const handleEmergencyStop = async () => {
    try {
      await apiClient.post('/api/v1/rc/emergency_stop');
      await fetchStatus();
    } catch (err) {
      setError('Failed to trigger emergency stop');
    }
  };

  // Handle channel configuration
  const handleChannelConfig = async () => {
    try {
      await apiClient.post('/api/v1/rc/channel/configure', {
        channel: selectedChannel,
        function: selectedFunction,
        min_value: 1000,
        max_value: 2000,
        center_value: 1500
      });
      await fetchChannels();
      setConfigDialogOpen(false);
    } catch (err) {
      setError('Failed to configure channel');
    }
  };

  // Get signal strength indicator
  const getSignalStrength = (channelValue: number) => {
    if (!channelValue || channelValue < 800 || channelValue > 2200) return 0;
    const normalized = Math.abs(channelValue - 1500) / 500;
    return Math.min(100, normalized * 100);
  };

  // Get status color
  const getStatusColor = () => {
    if (!status) return 'default';
    if (status.signal_lost) return 'error';
    if (!status.rc_enabled) return 'warning';
    return 'success';
  };

  if (loading) {
    return (
      <Box p={3}>
        <Typography variant="h4" gutterBottom>RC Control System</Typography>
        <LinearProgress />
        <Typography variant="body2" sx={{ mt: 1 }}>Loading RC control status...</Typography>
      </Box>
    );
  }

  return (
    <Box p={3}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">RC Control System</Typography>
        <Box>
          <Tooltip title="Refresh Status">
            <IconButton onClick={fetchStatus}>
              <Refresh />
            </IconButton>
          </Tooltip>
          <Tooltip title="Configure Channels">
            <IconButton onClick={() => setConfigDialogOpen(true)}>
              <Settings />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {!isConnected && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          WebSocket connection lost. RC status may not be real-time.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* System Status */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                System Status
                <Chip
                  size="small"
                  color={getStatusColor()}
                  icon={
                    status?.signal_lost ? <Error /> :
                    status?.rc_enabled ? <CheckCircle /> : <Warning />
                  }
                  label={
                    status?.signal_lost ? 'Signal Lost' :
                    status?.rc_enabled ? 'RC Active' : 'Autonomous'
                  }
                  sx={{ ml: 2 }}
                />
              </Typography>

              <Box display="flex" alignItems="center" mb={2}>
                <Typography variant="body2" sx={{ mr: 2 }}>RC Control:</Typography>
                <Switch
                  checked={status?.rc_enabled || false}
                  onChange={(e) => handleRCToggle(e.target.checked)}
                  color="primary"
                />
                <Typography variant="body2" sx={{ ml: 1 }}>
                  {status?.rc_enabled ? 'Enabled' : 'Disabled'}
                </Typography>
              </Box>

              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>RC Mode</InputLabel>
                <Select
                  value={status?.rc_mode || 'emergency'}
                  onChange={handleModeChange}
                  disabled={!status?.rc_enabled}
                >
                  {RC_MODES.map((mode) => (
                    <MenuItem key={mode.value} value={mode.value}>
                      <Box>
                        <Typography variant="body2">{mode.label}</Typography>
                        <Typography variant="caption" color="textSecondary">
                          {mode.description}
                        </Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Box display="flex" alignItems="center" mb={2}>
                <Typography variant="body2" sx={{ mr: 2 }}>Blade Motor:</Typography>
                <Switch
                  checked={status?.blade_enabled || false}
                  onChange={(e) => handleBladeToggle(e.target.checked)}
                  disabled={!status?.rc_enabled || status?.rc_mode === 'emergency'}
                  color="warning"
                />
                <Typography variant="body2" sx={{ ml: 1 }}>
                  {status?.blade_enabled ? 'Running' : 'Stopped'}
                </Typography>
              </Box>

              <Typography variant="body2" sx={{ mb: 1 }}>
                Encoder Position: {status?.encoder_position || 0}
              </Typography>

              <Divider sx={{ my: 2 }} />

              <Button
                variant="contained"
                color="error"
                startIcon={<Emergency />}
                onClick={handleEmergencyStop}
                fullWidth
                sx={{ mt: 1 }}
              >
                Emergency Stop
              </Button>
            </CardContent>
          </Card>
        </Grid>

        {/* Channel Status */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                RC Channel Status
              </Typography>

              {Object.entries(channels).map(([channelNum, config]) => {
                const channelValue = status?.channels?.[parseInt(channelNum)] || 1500;
                const signalStrength = getSignalStrength(channelValue);

                return (
                  <Box key={channelNum} sx={{ mb: 2 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center">
                      <Typography variant="body2">
                        Ch{channelNum}: {config.function}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        {channelValue}μs
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={signalStrength}
                      color={signalStrength > 50 ? 'success' : signalStrength > 20 ? 'warning' : 'error'}
                      sx={{ mt: 0.5, height: 6, borderRadius: 3 }}
                    />
                  </Box>
                );
              })}

              {Object.keys(channels).length === 0 && (
                <Typography variant="body2" color="textSecondary">
                  No channel configuration available
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Safety Information */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Safety Information
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={12} md={4}>
                  <Alert severity="info" variant="outlined">
                    <Typography variant="subtitle2">Emergency Mode</Typography>
                    <Typography variant="body2">
                      RC control is active only for emergency situations. 
                      Most functions are disabled for safety.
                    </Typography>
                  </Alert>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Alert severity="warning" variant="outlined">
                    <Typography variant="subtitle2">Signal Loss</Typography>
                    <Typography variant="body2">
                      System automatically returns to safe mode if RC signal is lost for more than 1 second.
                    </Typography>
                  </Alert>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Alert severity="error" variant="outlined">
                    <Typography variant="subtitle2">Emergency Stop</Typography>
                    <Typography variant="body2">
                      Emergency stop immediately halts all movement and disables blade motor.
                    </Typography>
                  </Alert>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Channel Configuration Dialog */}
      <Dialog open={configDialogOpen} onClose={() => setConfigDialogOpen(false)}>
        <DialogTitle>Configure RC Channel</DialogTitle>
        <DialogContent>
          <FormControl fullWidth sx={{ mt: 2, mb: 2 }}>
            <InputLabel>Channel</InputLabel>
            <Select
              value={selectedChannel}
              onChange={(e) => setSelectedChannel(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5, 6].map((ch) => (
                <MenuItem key={ch} value={ch}>Channel {ch}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Function</InputLabel>
            <Select
              value={selectedFunction}
              onChange={(e) => setSelectedFunction(e.target.value)}
            >
              {CHANNEL_FUNCTIONS.map((func) => (
                <MenuItem key={func} value={func}>{func}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <Typography variant="body2" color="textSecondary">
            Channel configuration allows you to map RC transmitter channels to mower functions.
            Default values: Min=1000μs, Center=1500μs, Max=2000μs
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfigDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleChannelConfig} variant="contained">
            Configure
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RCControl;

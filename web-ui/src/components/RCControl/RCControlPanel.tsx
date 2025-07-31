import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Alert, AlertDescription } from '../ui/alert';
import { 
  Radio, 
  Power, 
  Settings, 
  AlertTriangle, 
  Play, 
  Square,
  Zap 
} from 'lucide-react';

interface RCStatus {
  rc_enabled: boolean;
  rc_mode: string;
  signal_lost: boolean;
  blade_enabled: boolean;
  channels: Record<number, number>;
  encoder_position: number;
  timestamp: string;
}

interface RCControlPanelProps {
  className?: string;
}

const RC_MODES = [
  { 
    value: 'emergency', 
    label: 'Emergency Override',
    description: 'RC control only for emergency situations',
    color: 'bg-red-500'
  },
  { 
    value: 'manual', 
    label: 'Full Manual',
    description: 'Complete manual control of all functions',
    color: 'bg-blue-500'
  },
  { 
    value: 'assisted', 
    label: 'Assisted Mode',
    description: 'Manual control with safety oversight',
    color: 'bg-yellow-500'
  },
  { 
    value: 'training', 
    label: 'Training Mode',
    description: 'Manual control with movement recording',
    color: 'bg-green-500'
  }
];

const CHANNEL_FUNCTIONS = {
  1: 'Steer',
  2: 'Throttle', 
  3: 'Blade',
  4: 'Speed Adj',
  5: 'Emergency',
  6: 'Mode Switch'
};

export const RCControlPanel: React.FC<RCControlPanelProps> = ({ className }) => {
  const [rcStatus, setRcStatus] = useState<RCStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isChangingMode, setIsChangingMode] = useState(false);

  const fetchRCStatus = async () => {
    try {
      const response = await fetch('/api/v1/rc/status');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();
      setRcStatus(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch RC status');
    } finally {
      setLoading(false);
    }
  };

  const handleModeChange = async (mode: string) => {
    if (!rcStatus || isChangingMode) return;
    
    setIsChangingMode(true);
    try {
      const response = await fetch('/api/v1/rc/mode', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ mode }),
      });

      if (!response.ok) {
        throw new Error(`Failed to change RC mode: ${response.statusText}`);
      }

      await fetchRCStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change RC mode');
    } finally {
      setIsChangingMode(false);
    }
  };

  const handleRCControlToggle = async () => {
    if (!rcStatus) return;

    try {
      const endpoint = rcStatus.rc_enabled ? '/api/v1/rc/disable' : '/api/v1/rc/enable';
      const response = await fetch(endpoint, { method: 'POST' });

      if (!response.ok) {
        throw new Error(`Failed to toggle RC control: ${response.statusText}`);
      }

      await fetchRCStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle RC control');
    }
  };

  const handleBladeToggle = async () => {
    if (!rcStatus) return;

    try {
      const response = await fetch('/api/v1/rc/blade', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled: !rcStatus.blade_enabled }),
      });

      if (!response.ok) {
        throw new Error(`Failed to toggle blade: ${response.statusText}`);
      }

      await fetchRCStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle blade');
    }
  };

  const handleEmergencyStop = async () => {
    try {
      const response = await fetch('/api/v1/rc/emergency_stop', { method: 'POST' });

      if (!response.ok) {
        throw new Error(`Failed to trigger emergency stop: ${response.statusText}`);
      }

      await fetchRCStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger emergency stop');
    }
  };

  useEffect(() => {
    fetchRCStatus();
    const interval = setInterval(fetchRCStatus, 2000); // Update every 2 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Radio className="h-5 w-5" />
            RC Control System
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const currentMode = RC_MODES.find(m => m.value === rcStatus?.rc_mode);

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Radio className="h-5 w-5" />
          RC Control System
          {rcStatus?.signal_lost && (
            <Badge variant="destructive" className="ml-auto">
              Signal Lost
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {rcStatus && (
          <>
            {/* Control Status */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">RC Control</label>
                <div className="flex items-center gap-2">
                  <Badge variant={rcStatus.rc_enabled ? "default" : "secondary"}>
                    {rcStatus.rc_enabled ? "Enabled" : "Disabled"}
                  </Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleRCControlToggle}
                  >
                    <Power className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Blade Control</label>
                <div className="flex items-center gap-2">
                  <Badge variant={rcStatus.blade_enabled ? "destructive" : "secondary"}>
                    {rcStatus.blade_enabled ? "ON" : "OFF"}
                  </Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleBladeToggle}
                    disabled={!rcStatus.rc_enabled || rcStatus.signal_lost}
                  >
                    <Zap className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>

            {/* RC Mode Selection */}
            <div className="space-y-3">
              <label className="text-sm font-medium">Control Mode</label>
              <div className="grid grid-cols-2 gap-2">
                {RC_MODES.map((mode) => (
                  <Button
                    key={mode.value}
                    variant={rcStatus.rc_mode === mode.value ? "default" : "outline"}
                    size="sm"
                    className="justify-start text-left h-auto py-2"
                    onClick={() => handleModeChange(mode.value)}
                    disabled={isChangingMode || !rcStatus.rc_enabled}
                  >
                    <div>
                      <div className="font-medium">{mode.label}</div>
                      <div className="text-xs opacity-70">{mode.description}</div>
                    </div>
                  </Button>
                ))}
              </div>
            </div>

            {/* Channel Status */}
            <div className="space-y-3">
              <label className="text-sm font-medium">Channel Status</label>
              <div className="grid grid-cols-3 gap-2 text-xs">
                {Object.entries(CHANNEL_FUNCTIONS).map(([channel, func]) => {
                  const value = rcStatus.channels[parseInt(channel)] || 1500;
                  const isActive = Math.abs(value - 1500) > 50;
                  
                  return (
                    <div 
                      key={channel}
                      className={`p-2 rounded border ${isActive ? 'bg-blue-50 border-blue-200' : 'bg-gray-50'}`}
                    >
                      <div className="font-medium">CH{channel}: {func}</div>
                      <div className="text-gray-600">{value}μs</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Emergency Stop */}
            <div className="pt-4 border-t">
              <Button
                variant="destructive"
                className="w-full"
                onClick={handleEmergencyStop}
              >
                <Square className="h-4 w-4 mr-2" />
                Emergency Stop
              </Button>
            </div>

            {/* Status Info */}
            <div className="text-xs text-gray-500 pt-2 border-t">
              <div>Encoder: {rcStatus.encoder_position}</div>
              <div>Last Update: {new Date(rcStatus.timestamp).toLocaleTimeString()}</div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default RCControlPanel;

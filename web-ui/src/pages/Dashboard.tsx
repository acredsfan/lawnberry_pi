import React, { useEffect, useState } from 'react'
import { Grid, Card, CardContent, Typography, Box, LinearProgress, Chip, IconButton } from '@mui/material'
import { Battery90 as BatteryIcon, Thermostat as TempIcon, Speed as SpeedIcon, LocationOn as LocationIcon, Refresh as RefreshIcon } from '@mui/icons-material'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '../store/store'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { format } from 'date-fns'

const Dashboard: React.FC = () => {
  const dispatch = useDispatch()
  const { status, isConnected } = useSelector((state: RootState) => state.mower)
  const { data: weatherData } = useSelector((state: RootState) => state.weather)
  const { connectionStatus } = useSelector((state: RootState) => state.ui)
  
  const [sensorHistory, setSensorHistory] = useState<Array<{
    time: string
    battery: number
    temperature: number
    speed: number
  }>>([])

  const [videoStream, setVideoStream] = useState<string | null>(null)

  useEffect(() => {
    // Simulate real-time data updates
    const interval = setInterval(() => {
      if (status) {
        const newDataPoint = {
          time: format(new Date(), 'HH:mm:ss'),
          battery: status.battery.level,
          temperature: status.sensors.environmental.temperature,
          speed: Math.sqrt(
            Math.pow(status.sensors.imu.acceleration.x, 2) +
            Math.pow(status.sensors.imu.acceleration.y, 2)
          ) * 3.6 // Convert to km/h approximation
        }
        
        setSensorHistory(prev => {
          const updated = [...prev, newDataPoint]
          return updated.slice(-20) // Keep last 20 data points
        })
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [status])

  useEffect(() => {
    // Set up video stream
    const streamUrl = process.env.NODE_ENV === 'development' 
      ? 'http://localhost:8000/api/v1/camera/stream'
      : `/api/v1/camera/stream`
    setVideoStream(streamUrl)
  }, [])

  const getBatteryColor = (level: number) => {
    if (level > 60) return 'success'
    if (level > 30) return 'warning'
    return 'error'
  }

  const getStatusColor = (state: string) => {
    switch (state) {
      case 'mowing': return 'success'
      case 'charging': return 'info'
      case 'returning': return 'warning'
      case 'error': return 'error'
      case 'emergency': return 'error'
      default: return 'default'
    }
  }

  if (!isConnected) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="400px">
        <Typography variant="h6" color="text.secondary">
          Connecting to mower system...
        </Typography>
      </Box>
    )
  }

  return (
    <Box sx={{ width: '100%', height: '100%', overflow: 'auto' }}>
      <Grid container spacing={3}>
        {/* Status Overview */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h5" component="h2">
                  System Status
                </Typography>
                <IconButton size="small">
                  <RefreshIcon />
                </IconButton>
              </Box>
              
              <Grid container spacing={2}>
                <Grid item xs={6} sm={3}>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Chip 
                      label={status?.state.toUpperCase() || 'UNKNOWN'}
                      color={getStatusColor(status?.state || 'idle')}
                      size="small"
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    Current State
                  </Typography>
                </Grid>
                
                <Grid item xs={6} sm={3}>
                  <Box display="flex" alignItems="center" gap={1}>
                    <LocationIcon fontSize="small" />
                    <Box>
                      <Typography variant="body2">
                        {status?.position ? 
                          `${status.position.lat.toFixed(6)}, ${status.position.lng.toFixed(6)}` :
                          'No Location'
                        }
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {status?.location_source === 'gps_hardware' ? 'GPS' : 
                         status?.location_source === 'config_fallback' ? 'Config' : 'Unknown'}
                      </Typography>
                    </Box>
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    Position
                  </Typography>
                </Grid>
                
                <Grid item xs={6} sm={3}>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2">
                      {status?.coverage ? `${status.coverage.percentage.toFixed(1)}%` : '0%'}
                    </Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    Coverage
                  </Typography>
                </Grid>
                
                <Grid item xs={6} sm={3}>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2">
                      {weatherData?.current.condition || 'Unknown'}
                    </Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    Weather
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Camera Feed */}
        <Grid item xs={12} md={8}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Live Camera Feed
              </Typography>
              <Box className="camera-feed" sx={{ height: 320, backgroundColor: '#000', borderRadius: 1, position: 'relative' }}>
                {videoStream ? (
                  <>
                    <img 
                      src={videoStream}
                      alt="Live camera feed"
                      style={{ 
                        width: '100%', 
                        height: '100%', 
                        objectFit: 'cover',
                        borderRadius: 4
                      }}
                      onError={() => setVideoStream(null)}
                    />
                    <Box className="camera-overlay">
                      {/* Overlay for detected objects would go here */}
                    </Box>
                  </>
                ) : (
                  <Box display="flex" justifyContent="center" alignItems="center" height="100%" color="white">
                    <Typography>Camera feed unavailable</Typography>
                  </Box>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Battery Status */}
        <Grid item xs={12} md={4}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={2}>
                <BatteryIcon />
                <Typography variant="h6">
                  Battery Status
                </Typography>
              </Box>
              
              <Box sx={{ mb: 3 }}>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Charge Level</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {status?.battery.level || 0}%
                  </Typography>
                </Box>
                <LinearProgress 
                  variant="determinate" 
                  value={status?.battery.level || 0}
                  color={getBatteryColor(status?.battery.level || 0)}
                  sx={{ height: 8, borderRadius: 4 }}
                />
              </Box>

              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Voltage</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {status?.battery.voltage.toFixed(2) || '0.00'}V
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Current</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {status?.battery.current.toFixed(2) || '0.00'}A
                  </Typography>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">Charging</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {status?.battery.charging ? 'Yes' : 'No'}
                  </Typography>
                </Grid>
                {status?.battery.timeRemaining && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Time Remaining</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {Math.floor(status.battery.timeRemaining / 60)}h {status.battery.timeRemaining % 60}m
                    </Typography>
                  </Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Sensor Data Chart */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Real-time Sensor Data
              </Typography>
              <Box className="chart-container">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={sensorHistory}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <Tooltip />
                    <Line 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="battery" 
                      stroke="#4caf50" 
                      strokeWidth={2}
                      name="Battery (%)"
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="temperature" 
                      stroke="#ff9800" 
                      strokeWidth={2}
                      name="Temperature (°C)"
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="speed" 
                      stroke="#2196f3" 
                      strokeWidth={2}
                      name="Speed (km/h)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}

export default Dashboard

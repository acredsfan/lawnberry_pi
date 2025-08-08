import React, { useEffect, useState } from 'react'
import { Grid, Card, CardContent, Typography, Box, LinearProgress, Chip, IconButton, Alert } from '@mui/material'
import { Battery90 as BatteryIcon, Thermostat as TempIcon, Speed as SpeedIcon, LocationOn as LocationIcon, Refresh as RefreshIcon } from '@mui/icons-material'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '../store/store'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { format } from 'date-fns'
import { setStatus, setConnectionState } from '../store/slices/mowerSlice'
import { dataService } from '../services/dataService'
import { useUnits } from '../hooks/useUnits'
import { MowerStatus } from '../types'
import { batteryLevelColor, guardDottedPaletteMisuse } from '../utils/color'

const Dashboard: React.FC = () => {
  const dispatch = useDispatch()
  const { status, isConnected } = useSelector((state: RootState) => state.mower)
  const { data: weatherData } = useSelector((state: RootState) => state.weather)
  const { connectionStatus } = useSelector((state: RootState) => state.ui)
    const { format: formatUnits, convert: converters, unitPreferences: unitsPrefs } = useUnits()
  
  const [sensorHistory, setSensorHistory] = useState<Array<{
    time: string
    battery: number
    temperature: number
    speed: number
  }>>([])

  const [videoStream, setVideoStream] = useState<string | null>(null)
  const [realDataActive, setRealDataActive] = useState(false)
  const [lastDataUpdate, setLastDataUpdate] = useState<Date | null>(null)

  // Initialize real data service
  useEffect(() => {
    let unsubscribe: (() => void) | null = null

    const initializeDataService = async () => {
      try {
        // Check if backend is available
        const isBackendAvailable = await dataService.checkConnectivity()
        
        if (isBackendAvailable) {
          setRealDataActive(true)
          dispatch(setConnectionState(true))
          
          // Subscribe to status updates from data service
          unsubscribe = dataService.subscribe((newStatus: MowerStatus) => {
            dispatch(setStatus(newStatus))
            setLastDataUpdate(new Date())
          })
          
          // Start polling every 3 seconds for real-time updates
          dataService.startStatusPolling(3000)
          
          if (import.meta.env.DEV) console.log('✅ Real data service activated - polling backend every 3 seconds')
        } else {
          setRealDataActive(false)
          if (import.meta.env.DEV) console.warn('⚠️ Backend not available, using fallback mock data')
          
          // Set fallback data immediately
          const fallbackStatus: MowerStatus = {
            state: 'idle',
            position: { lat: 40.7128, lng: -74.0060, heading: 0, accuracy: 5 },
            battery: { level: 75.3, voltage: 24.1, current: 1.8, charging: false, timeRemaining: 120 },
            sensors: {
              imu: {
                orientation: { x: 0, y: 0, z: 0 },
                acceleration: { x: 0, y: 0, z: 9.8 },
                gyroscope: { x: 0, y: 0, z: 0 },
                temperature: 35
              },
              tof: { left: 1.2, right: 1.5 },
              environmental: { temperature: 22, humidity: 65, pressure: 1013 },
              power: { voltage: 24.1, current: 1.8, power: 43.4 }
            },
            coverage: { totalArea: 1000, coveredArea: 450, percentage: 45 },
            lastUpdate: Date.now() / 1000,
            location_source: 'gps',
            connected: false
          }
          dispatch(setStatus(fallbackStatus))
          dispatch(setConnectionState(false))
        }
      } catch (error) {
        if (import.meta.env.DEV) console.error('Failed to initialize data service:', error)
        setRealDataActive(false)
      }
    }

    initializeDataService()

    // Cleanup on unmount
    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
      dataService.stopStatusPolling()
    }
  }, [dispatch])

  useEffect(() => {
    // Simulate real-time data updates
    const interval = setInterval(() => {
      if (status && status.battery && status.sensors?.environmental && status.sensors?.imu) {
        const newDataPoint = {
          time: format(new Date(), 'HH:mm:ss'),
          battery: typeof status.battery.level === 'number' ? status.battery.level : 0,
          temperature: converters.temperature(status.sensors.environmental?.temperature ?? 0).value,
          speed: converters.speed(Math.sqrt(
            Math.pow(status.sensors.imu.acceleration?.x || 0, 2) +
            Math.pow(status.sensors.imu.acceleration?.y || 0, 2)
          )).value // Convert from m/s to current unit system
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

  const getBatteryColor = (level?: number) => {
    if (typeof level !== 'number') return 'default'
    if (level > 60) return 'success'
    if (level > 30) return 'warning'
    return 'error'
  }

  const getStatusColor = (state: string) => {
    switch (state) {
      case 'mowing': return 'success'
      case 'charging': return 'info'
      case 'returning': return 'warning'
      case 'error':
      case 'emergency': return 'error'
      case 'idle': return 'secondary'
      default: return 'info'
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
    <Box sx={{ width: '100%', height: '100%', overflow: 'auto' }} className="retro-grid">
      <Grid container spacing={3}>
        {/* Status Overview */}
        <Grid item xs={12}>
          <Card className="holographic">
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h4" component="h2" className="neon-text">
                  SYSTEM STATUS
                </Typography>
                <Box display="flex" alignItems="center" gap={2}>
                  {realDataActive && (
                    <Chip 
                      label="LIVE DATA" 
                      color="success" 
                      size="small"
                      className="pulse"
                      sx={{ 
                        fontFamily: 'monospace',
                        fontWeight: 'bold',
                        animation: 'pulse 2s infinite'
                      }}
                    />
                  )}
                  {lastDataUpdate && (
                    <Typography variant="caption" color="text.secondary">
                      Updated: {format(lastDataUpdate, 'HH:mm:ss')}
                    </Typography>
                  )}
                  <IconButton 
                    size="small" 
                    sx={{ 
                      color: 'primary.main',
                      '&:hover': { 
                        color: 'secondary.main',
                        transform: 'rotate(180deg)',
                        transition: 'all 0.3s ease'
                      }
                    }}
                  >
                    <RefreshIcon />
                  </IconButton>
                </Box>
              </Box>
              
              <Grid container spacing={3}>
                <Grid item xs={6} sm={3}>
                  <Box display="flex" flexDirection="column" alignItems="center" gap={1}>
                    <Chip 
                      label={status?.state?.toUpperCase() || 'UNKNOWN'}
                      color={getStatusColor(status?.state || 'idle')}
                      size="medium"
                      sx={{ 
                        fontSize: '1.1rem', 
                        fontWeight: 900,
                        minWidth: '120px',
                        animation: 'pulse-glow 2s ease-in-out infinite'
                      }}
                    />
                    <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                      Current State
                    </Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={6} sm={3}>
                  <Box display="flex" flexDirection="column" alignItems="center" gap={1}>
                    <Box display="flex" alignItems="center" gap={1}>
                      <LocationIcon sx={{ color: 'primary.main', filter: 'drop-shadow(0 0 5px currentColor)' }} />
                      <Box>
                        <Typography variant="body2" className="neon-text" sx={{ fontFamily: 'monospace' }}>
                          {status?.position ? 
                            `${status.position.lat.toFixed(6)}, ${status.position.lng.toFixed(6)}` :
                            'NO SIGNAL'
                          }
                        </Typography>
                        <Chip 
                          size="small"
                          label={status?.location_source === 'gps' ? 'GPS ACTIVE' : 
                                 status?.location_source === 'config' ? 'CONFIG MODE' : 'UNKNOWN'}
                          color={status?.location_source === 'gps' ? 'success' : 'warning'}
                        />
                      </Box>
                    </Box>
                    <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                      Position Lock
                    </Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={6} sm={3}>
                  <Box display="flex" flexDirection="column" alignItems="center" gap={1}>
                    <Typography variant="h3" className="neon-text" sx={{ fontFamily: 'monospace', fontWeight: 900 }}>
                        {status?.coverage?.percentage != null ? status.coverage.percentage.toFixed(1) : '0'}%
                    </Typography>
                    <LinearProgress 
                      variant="determinate" 
                      value={status?.coverage?.percentage || 0}
                      sx={{ 
                        width: '100%', 
                        height: 8, 
                        background: 'rgba(0, 255, 209, 0.2)',
                        '& .MuiLinearProgress-bar': {
                          background: 'linear-gradient(90deg, #00FFD1, #FF1493)',
                          boxShadow: '0 0 10px currentColor'
                        }
                      }}
                    />
                    <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                      Area Coverage
                    </Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={6} sm={3}>
                  <Box display="flex" flexDirection="column" alignItems="center" gap={1}>
                    <Typography variant="h5" className="neon-text-secondary" sx={{ fontFamily: 'monospace' }}>
                      {weatherData?.current.condition || 'UNKNOWN'}
                    </Typography>
                    <Typography variant="body2" className="neon-text" sx={{ fontFamily: 'monospace' }}>
                      {weatherData?.current.temperature ? formatUnits.temperature(weatherData.current.temperature) : `--${formatUnits.temperature(0).split('0')[1]}`}
                    </Typography>
                    <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                      Weather Status
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Camera Feed */}
        <Grid item xs={12} md={8}>
          <Card sx={{ height: 450 }} className="holographic">
            <CardContent>
              <Typography variant="h5" gutterBottom className="neon-text" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                LIVE CAMERA FEED
              </Typography>
              <Box className="camera-feed" sx={{ height: 380, backgroundColor: '#000', position: 'relative' }}>
                {videoStream ? (
                  <>
                    <img 
                      src={videoStream}
                      alt="Live camera feed"
                      style={{ 
                        width: '100%', 
                        height: '100%', 
                        objectFit: 'cover'
                      }}
                      onError={() => setVideoStream(null)}
                    />
                    <Box className="camera-overlay" />
                  </>
                ) : (
                  <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" height="100%" gap={2}>
                    <Typography variant="h6" className="neon-text-secondary">
                      CAMERA OFFLINE
                    </Typography>
                    <Typography variant="body2" className="neon-text" sx={{ fontFamily: 'monospace' }}>
                      [NO SIGNAL DETECTED]
                    </Typography>
                    <Box sx={{ 
                      width: 200, 
                      height: 4, 
                      background: 'linear-gradient(90deg, transparent, #FF073A, transparent)',
                      animation: 'neon-border 2s linear infinite'
                    }} />
                  </Box>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Battery Status */}
        <Grid item xs={12} md={4}>
          <Card sx={{ height: 450 }} className="holographic">
            <CardContent>
              <Box display="flex" alignItems="center" gap={2} mb={3}>
                <BatteryIcon
                  sx={(theme) => {
                    const sxObj = {
                      fontSize: '2rem',
                      color: batteryLevelColor(theme, status?.battery?.level),
                      filter: 'drop-shadow(0 0 10px currentColor)'
                    } as const
                    guardDottedPaletteMisuse(sxObj, 'Dashboard.BatteryIcon')
                    return sxObj
                  }}
                />
                <Typography variant="h5" className="neon-text" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                  POWER CORE
                </Typography>
              </Box>
              
              <Box sx={{ mb: 4 }}>
                <Box display="flex" justifyContent="space-between" mb={2}>
                  <Typography variant="body2" className="neon-text-secondary" sx={{ textTransform: 'uppercase' }}>
                    Charge Level
                  </Typography>
                  <Typography variant="h4" className="neon-text" sx={{ fontFamily: 'monospace', fontWeight: 900 }}>
                    {typeof status?.battery?.level === 'number' ? status.battery.level.toFixed(1) : '0.0'}%
                  </Typography>
                </Box>
                <LinearProgress 
                  variant="determinate" 
                  value={typeof status?.battery?.level === 'number' ? status.battery.level : 0}
                  // We intentionally avoid the MUI color prop (only primary/secondary supported for LinearProgress)
                  // and instead style via sx so success/warning/error palette shades are applied safely.
                  sx={(theme) => {
                    const lvl = typeof status?.battery?.level === 'number' ? status.battery.level : 0
                    const barColor = batteryLevelColor(theme, lvl)
                    const sxObj = {
                      height: 16,
                      border: '1px solid rgba(255,255,255,0.15)',
                      backgroundColor: 'rgba(0,0,0,0.7)',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: barColor,
                        boxShadow: `0 0 20px ${barColor}`
                      }
                    } as const
                    guardDottedPaletteMisuse(sxObj, 'Dashboard.BatteryProgress')
                    return sxObj
                  }}
                />
              </Box>

              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase' }}>
                    Voltage
                  </Typography>
                  <Typography variant="h6" className="neon-text" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                    {typeof status?.battery?.voltage === 'number' ? status.battery.voltage.toFixed(2) : '0.00'}V
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase' }}>
                    Current
                  </Typography>
                  <Typography variant="h6" className="neon-text" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                    {typeof status?.battery?.current === 'number' ? status.battery.current.toFixed(2) : '0.00'}A
                  </Typography>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase' }}>
                    Charging Status
                  </Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="h6" className="neon-text" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                      {status?.battery?.charging ? 'CHARGING' : 'DISCHARGING'}
                    </Typography>
                    <Box 
                      className={`status-indicator ${status?.battery?.charging ? 'status-online' : 'status-warning'}`}
                    />
                  </Box>
                </Grid>
                {status?.battery?.timeRemaining && (
                  <Grid item xs={12}>
                    <Typography variant="caption" className="neon-text-secondary" sx={{ textTransform: 'uppercase' }}>
                      Time Remaining
                    </Typography>
                    <Typography variant="h6" className="neon-text" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                      {Math.floor((status.battery?.timeRemaining || 0) / 60)}H {(status.battery?.timeRemaining || 0) % 60}M
                    </Typography>
                  </Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Sensor Data Chart */}
        <Grid item xs={12}>
          <Card className="holographic">
            <CardContent>
              <Typography variant="h5" gutterBottom className="neon-text" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                REAL-TIME SENSOR DATA
              </Typography>
              <Box className="chart-container">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={sensorHistory} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0, 255, 209, 0.3)" />
                    <XAxis 
                      dataKey="time" 
                      stroke="#00FFD1" 
                      style={{ fontSize: '12px', fontFamily: 'monospace' }}
                    />
                    <YAxis 
                      yAxisId="left" 
                      stroke="#00FFD1" 
                      style={{ fontSize: '12px', fontFamily: 'monospace' }}
                    />
                    <YAxis 
                      yAxisId="right" 
                      orientation="right" 
                      stroke="#FF1493" 
                      style={{ fontSize: '12px', fontFamily: 'monospace' }}
                    />
                    <Tooltip 
                      contentStyle={{
                        backgroundColor: '#1a1a2e',
                        border: '2px solid #00FFD1',
                        borderRadius: 0,
                        boxShadow: '0 0 20px rgba(0, 255, 209, 0.5)',
                        fontFamily: 'monospace',
                        color: '#FFFFFF'
                      }}
                    />
                    <Line 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="battery" 
                      stroke="#39FF14" 
                      strokeWidth={3}
                      name="Battery (%)"
                      dot={{ fill: '#39FF14', strokeWidth: 2, r: 4 }}
                      activeDot={{ r: 6, stroke: '#39FF14', strokeWidth: 2, fill: '#39FF14' }}
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="temperature" 
                      stroke="#FFD700" 
                      strokeWidth={3}
                      name={`Temperature (${unitsPrefs.temperature})`}
                      dot={{ fill: '#FFD700', strokeWidth: 2, r: 4 }}
                      activeDot={{ r: 6, stroke: '#FFD700', strokeWidth: 2, fill: '#FFD700' }}
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="speed" 
                      stroke="#FF1493" 
                      strokeWidth={3}
                      name={`Speed (${unitsPrefs.system === 'metric' ? 'km/h' : 'mph'})`}
                      dot={{ fill: '#FF1493', strokeWidth: 2, r: 4 }}
                      activeDot={{ r: 6, stroke: '#FF1493', strokeWidth: 2, fill: '#FF1493' }}
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

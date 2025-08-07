import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Box, Snackbar, Alert, CircularProgress, Typography, Button } from '@mui/material'
import { useDispatch, useSelector } from 'react-redux'
import { RootState } from './store/store'
import { addNotification, setConnectionStatus, updateActivity } from './store/slices/uiSlice'
import { setStatus, updateStatus, setConnectionState } from './store/slices/mowerSlice'
import { setWeatherData } from './store/slices/weatherSlice'
import Layout from './components/Layout/Layout'
import Dashboard from './pages/Dashboard'
import Navigation from './pages/Navigation'
import Maps from './pages/Maps'
import Settings from './pages/Settings'
import Training from './pages/Training'
import RCControl from './pages/RCControl'
import Documentation from './pages/Documentation'
import Logo from './components/Logo'
import { webSocketService } from './services/websocket'
import { sensorDataService } from './services/sensorDataService'
import { usePerformanceMonitor } from './hooks/usePerformanceMonitor'
import { useUnits } from './hooks/useUnits'

const AppContent: React.FC = () => {
  const location = useLocation()
  
  // Define routes that should use full-page mode on desktop
  const fullPageRoutes = ['/maps', '/dashboard']
  const shouldUseFullPage = fullPageRoutes.includes(location.pathname)

  return (
    <Layout fullPageMode={shouldUseFullPage}>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/navigation" element={<Navigation />} />
        <Route path="/maps" element={<Maps />} />
        <Route path="/rc-control" element={<RCControl />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/training" element={<Training />} />
        <Route path="/documentation" element={<Documentation />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Layout>
  )
}

const App: React.FC = () => {
  const dispatch = useDispatch()
  const { notifications, connectionStatus } = useSelector((state: RootState) => state.ui)
  const [initializing, setInitializing] = useState(true)
  const [initError, setInitError] = useState<string | null>(null)
  const [notification, setNotification] = useState<{ open: boolean; message: string; severity: 'success' | 'info' | 'warning' | 'error' }>({
    open: false,
    message: '',
    severity: 'info'
  })

  usePerformanceMonitor()
  useUnits() // Initialize units system

  useEffect(() => {
    // Emergency timeout to show app no matter what after 5 seconds
    const emergencyTimeout = setTimeout(() => {
      if (initializing) {
        console.log('🚨 EMERGENCY: Forcing app to show after timeout')
        setInitError('Initialization took too long - showing interface anyway')
        setInitializing(false)
      }
    }, 5000)

    const initializeApp = async () => {
      console.log('🚀 Starting LawnBerryPi app initialization...')
      
      try {
        dispatch(setConnectionStatus('connecting'))
        
        // Initialize with mock data for demonstration
        const mockMowerStatus = {
          state: 'idle' as const,
          position: {
            lat: 40.7128,
            lng: -74.0060,
            heading: 90,
            accuracy: 5
          },
          battery: {
            level: 78,
            voltage: 24.2,
            current: 1.8,
            charging: false,
            timeRemaining: 145
          },
          sensors: {
            imu: {
              orientation: { x: 0.1, y: -0.2, z: 0.0 },
              acceleration: { x: 0.0, y: 0.0, z: 9.81 },
              gyroscope: { x: 0.01, y: -0.02, z: 0.00 },
              temperature: 35.6
            },
            tof: {
              left: 1.2,
              right: 0.8
            },
            environmental: {
              temperature: 24.5,
              humidity: 65,
              pressure: 1013.25
            },
            power: {
              voltage: 24.2,
              current: 1.8,
              power: 43.56
            }
          },
          coverage: {
            totalArea: 1000,
            coveredArea: 750,
            percentage: 75.0
          },
          lastUpdate: Date.now(),
          location_source: 'gps' as const,
          connected: true
        }

        const mockWeatherData = {
          current: {
            temperature: 24.5,
            humidity: 65,
            windSpeed: 3.2,
            windDirection: 180,
            precipitation: 0,
            condition: 'Partly Cloudy',
            icon: 'partly-cloudy'
          },
          forecast: [
            {
              date: new Date().toISOString().split('T')[0],
              temperature: { min: 18, max: 28 },
              condition: 'Sunny',
              icon: 'sunny',
              precipitation: 0
            }
          ],
          alerts: []
        }
        
        // Set initial mock data immediately
        dispatch(setStatus(mockMowerStatus))
        dispatch(setWeatherData(mockWeatherData))
        
        console.log('✅ Mock data initialized')

        // Set up WebSocket event handlers early
        webSocketService.on('connect', () => {
          console.log('� WebSocket connected')
          dispatch(setConnectionStatus('connected'))
          dispatch(setConnectionState(true))
          dispatch(addNotification({
            type: 'success',
            title: 'Connected',
            message: 'Successfully connected to mower system'
          }))
        })

        webSocketService.on('disconnect', () => {
          console.log('🔗 WebSocket disconnected')
          dispatch(setConnectionStatus('disconnected'))
          dispatch(setConnectionState(false))
          dispatch(addNotification({
            type: 'warning',
            title: 'Disconnected',
            message: 'Lost connection to mower system'
          }))
        })

        webSocketService.on('error', (error) => {
          console.log('🔗 WebSocket error:', error)
          dispatch(setConnectionStatus('error'))
          dispatch(addNotification({
            type: 'error',
            title: 'Connection Error',
            message: error.message || 'Failed to connect to mower system'
          }))
        })

        // Track user activity
        const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart']
        const updateUserActivity = () => dispatch(updateActivity())
        
        activityEvents.forEach(event => {
          document.addEventListener(event, updateUserActivity, true)
        })

        console.log('🎉 Basic initialization complete')
        
        // Show app immediately with a short delay to ensure rendering
        setTimeout(() => {
          console.log('🎨 Showing UI...')
          clearTimeout(emergencyTimeout)
          setInitializing(false)
          dispatch(setConnectionStatus('connected'))
        }, 250)

        // Initialize background services after UI is shown (non-blocking)
        setTimeout(() => {
          console.log('🔌 Starting background services...')
          
          // Try to connect WebSocket (non-critical)
          try {
            console.log('🌐 Attempting WebSocket connection...')
            webSocketService.connect()
          } catch (error) {
            console.warn('⚠️ WebSocket connection failed:', error)
          }

          // Try to start sensor data service (non-critical)
          try {
            console.log('📊 Starting sensor data service...')
            
            const unsubscribeSensorData = sensorDataService.subscribe((sensorData) => {
              // Update mower status with real sensor data
              const updatedStatus = {
                state: 'idle' as const,
                position: {
                  lat: sensorData.gps.latitude || mockMowerStatus.position.lat,
                  lng: sensorData.gps.longitude || mockMowerStatus.position.lng,
                  heading: sensorData.imu.orientation.yaw || mockMowerStatus.position.heading,
                  accuracy: sensorData.gps.accuracy || mockMowerStatus.position.accuracy
                },
                battery: {
                  level: sensorData.power.battery_level || mockMowerStatus.battery.level,
                  voltage: sensorData.power.battery_voltage || mockMowerStatus.battery.voltage,
                  current: sensorData.power.battery_current || mockMowerStatus.battery.current,
                  charging: sensorData.power.charging || mockMowerStatus.battery.charging,
                  timeRemaining: Math.floor((sensorData.power.battery_level || mockMowerStatus.battery.level) * 2)
                },
                sensors: {
                  imu: {
                    orientation: { 
                      x: sensorData.imu.orientation.roll || mockMowerStatus.sensors.imu.orientation.x,
                      y: sensorData.imu.orientation.pitch || mockMowerStatus.sensors.imu.orientation.y,
                      z: sensorData.imu.orientation.yaw || mockMowerStatus.sensors.imu.orientation.z
                    },
                    acceleration: sensorData.imu.acceleration || mockMowerStatus.sensors.imu.acceleration,
                    gyroscope: sensorData.imu.gyroscope || mockMowerStatus.sensors.imu.gyroscope,
                    temperature: sensorData.imu.temperature || mockMowerStatus.sensors.imu.temperature
                  },
                  tof: {
                    left: sensorData.tof.left_distance || mockMowerStatus.sensors.tof.left,
                    right: sensorData.tof.right_distance || mockMowerStatus.sensors.tof.right
                  },
                  environmental: {
                    temperature: sensorData.environmental.temperature || mockMowerStatus.sensors.environmental.temperature,
                    humidity: sensorData.environmental.humidity || mockMowerStatus.sensors.environmental.humidity,
                    pressure: sensorData.environmental.pressure || mockMowerStatus.sensors.environmental.pressure
                  },
                  power: {
                    voltage: sensorData.power.battery_voltage || mockMowerStatus.sensors.power.voltage,
                    current: sensorData.power.battery_current || mockMowerStatus.sensors.power.current,
                    power: (sensorData.power.battery_voltage || mockMowerStatus.sensors.power.voltage) * (sensorData.power.battery_current || mockMowerStatus.sensors.power.current)
                  }
                },
                coverage: mockMowerStatus.coverage,
                lastUpdate: Date.now(),
                location_source: 'gps' as const,
                connected: true
              }
              
              dispatch(setStatus(updatedStatus))
            })
            
            sensorDataService.start()
            console.log('📊 Sensor data service started')
          } catch (error) {
            console.warn('⚠️ Sensor data service failed to start:', error)
          }
        }, 500)

        // Cleanup function
        return () => {
          activityEvents.forEach(event => {
            document.removeEventListener(event, updateUserActivity, true)
          })
          
          try {
            sensorDataService.stop()
            webSocketService.disconnect()
          } catch (error) {
            console.warn('Error during cleanup:', error)
          }
        }
        
      } catch (error) {
        console.error('❌ Failed to initialize app:', error)
        const errorMessage = error instanceof Error ? error.message : 'Unknown initialization error'
        setInitError(errorMessage)
        
        // Always show the app, even if there are errors
        setTimeout(() => {
          console.log('⚠️ Showing app despite initialization error')
          clearTimeout(emergencyTimeout)
          setInitializing(false)
          dispatch(setConnectionStatus('error'))
        }, 500)
      }
    }

    initializeApp()
  }, [dispatch])

  useEffect(() => {
    // Show latest unread notification
    const latestNotification = notifications.find(n => !n.read)
    if (latestNotification) {
      setNotification({
        open: true,
        message: latestNotification.message,
        severity: latestNotification.type
      })
    }
  }, [notifications])

  const handleCloseNotification = () => {
    setNotification(prev => ({ ...prev, open: false }))
  }

  if (initializing) {
    return (
      <Box
        display="flex"
        flexDirection="column"
        justifyContent="center"
        alignItems="center"
        height="100vh"
        gap={3}
        sx={{ backgroundColor: 'background.default', p: 3 }}
      >
        <Logo size={80} showText={true} />
        {!initError ? (
          <>
            <CircularProgress size={48} thickness={4} />
            <Box textAlign="center">
              <Typography variant="h6" color="primary" gutterBottom>
                Initializing LawnBerryPi Control...
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Connecting to mower system
              </Typography>
            </Box>
          </>
        ) : (
          <Box textAlign="center">
            <Typography variant="h6" color="error" gutterBottom>
              Initialization Error
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {initError}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Loading interface anyway...
            </Typography>
            <CircularProgress size={32} thickness={4} sx={{ mb: 2 }} />
            <Button 
              variant="outlined" 
              onClick={() => {
                console.log('🔧 Manual override - showing app')
                setInitializing(false)
              }}
              sx={{ mt: 1 }}
            >
              Skip & Continue
            </Button>
          </Box>
        )}
      </Box>
    )
  }

  return (
    <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <AppContent />

      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={handleCloseNotification}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Alert
          onClose={handleCloseNotification}
          severity={notification.severity}
          sx={{ width: '100%' }}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  )
}

export default App

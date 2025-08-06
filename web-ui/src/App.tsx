import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Box, Snackbar, Alert, CircularProgress, Typography } from '@mui/material'
import { useDispatch, useSelector } from 'react-redux'
import { RootState } from './store/store'
import { addNotification, setConnectionStatus, updateActivity } from './store/slices/uiSlice'
import { setStatus, setConnectionState } from './store/slices/mowerSlice'
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
  const [notification, setNotification] = useState<{ open: boolean; message: string; severity: 'success' | 'info' | 'warning' | 'error' }>({
    open: false,
    message: '',
    severity: 'info'
  })

  usePerformanceMonitor()
  useUnits() // Initialize units system

  useEffect(() => {
    const initializeApp = async () => {
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
        
        // Set initial mock data
        dispatch(setStatus(mockMowerStatus))
        dispatch(setWeatherData(mockWeatherData))
        
        // Start real-time sensor data service
        const unsubscribeSensorData = sensorDataService.subscribe((sensorData) => {
          // Update mower status with real sensor data
          const updatedStatus = {
            state: 'idle' as const,
            position: {
              lat: sensorData.gps.latitude,
              lng: sensorData.gps.longitude,
              heading: sensorData.imu.orientation.yaw,
              accuracy: sensorData.gps.accuracy
            },
            battery: {
              level: sensorData.power.battery_level,
              voltage: sensorData.power.battery_voltage,
              current: sensorData.power.battery_current,
              charging: sensorData.power.charging,
              timeRemaining: Math.floor(sensorData.power.battery_level * 2) // Rough estimate
            },
            sensors: {
              imu: {
                orientation: sensorData.imu.orientation,
                acceleration: sensorData.imu.acceleration,
                gyroscope: sensorData.imu.gyroscope,
                temperature: sensorData.imu.temperature
              },
              tof: {
                left: sensorData.tof.left_distance,
                right: sensorData.tof.right_distance
              },
              environmental: {
                temperature: sensorData.environmental.temperature,
                humidity: sensorData.environmental.humidity,
                pressure: sensorData.environmental.pressure
              },
              power: {
                voltage: sensorData.power.battery_voltage,
                current: sensorData.power.battery_current,
                power: sensorData.power.battery_voltage * sensorData.power.battery_current
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
          
          dispatch(setStatus(updatedStatus))
          
          // Update weather data with environmental sensors
          const updatedWeatherData = {
            current: {
              temperature: sensorData.environmental.temperature,
              humidity: sensorData.environmental.humidity,
              windSpeed: 3.2,
              windDirection: 180,
              precipitation: sensorData.environmental.rain_detected ? 0.5 : 0,
              condition: sensorData.environmental.rain_detected ? 'Rainy' : 'Clear',
              icon: sensorData.environmental.rain_detected ? 'rain' : 'sunny'
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
          
          dispatch(setWeatherData(updatedWeatherData))
        })
        
        // Start the sensor data service
        sensorDataService.start()
        
        // Initialize WebSocket connection
        webSocketService.connect()
        
        // Set up WebSocket event handlers
        webSocketService.on('connect', () => {
          dispatch(setConnectionStatus('connected'))
          dispatch(setConnectionState(true))
          dispatch(addNotification({
            type: 'success',
            title: 'Connected',
            message: 'Successfully connected to mower system'
          }))
        })

        webSocketService.on('disconnect', () => {
          dispatch(setConnectionStatus('disconnected'))
          dispatch(setConnectionState(false))
          dispatch(addNotification({
            type: 'warning',
            title: 'Disconnected',
            message: 'Lost connection to mower system'
          }))
        })

        webSocketService.on('error', (error) => {
          dispatch(setConnectionStatus('error'))
          dispatch(addNotification({
            type: 'error',
            title: 'Connection Error',
            message: error.message || 'Failed to connect to mower system'
          }))
        })

        webSocketService.on('mqtt_data', (data, topic) => {
          // Handle MQTT data forwarded through WebSocket
          console.log('Received MQTT data:', topic, data)
          
          // Route data to appropriate store slices based on topic
          if (topic.startsWith('system/status')) {
            dispatch(setStatus(data))
          } else if (topic.startsWith('sensors/')) {
            // Handle sensor data
            if (data.sensor_type === 'environmental') {
              // Update weather-related sensor data
              dispatch(setWeatherData({
                current: {
                  temperature: data.temperature,
                  humidity: data.humidity,
                  condition: data.condition || 'unknown'
                }
              }))
            }
          } else if (topic.startsWith('power/battery')) {
            // Update battery status
            dispatch(setStatus({
              battery: data
            }))
          } else if (topic.startsWith('navigation/')) {
            // Update navigation data
            dispatch(setStatus({
              position: data.position,
              location_source: data.location_source
            }))
          } else if (topic.startsWith('weather/current')) {
            dispatch(setWeatherData(data))
          }
        })

        webSocketService.on('data', (data, topic) => {
          // Handle direct data messages
          console.log('Received direct data:', topic, data)
          // Process similar to mqtt_data
        })

        webSocketService.on('mower_status', (data) => {
          dispatch(setStatus(data))
        })

        webSocketService.on('weather_data', (data) => {
          dispatch(setWeatherData(data))
        })

        webSocketService.on('notification', (data) => {
          dispatch(addNotification(data))
        })

        // Remove the old data simulation since we now have real-time sensor data
        // const simulateDataUpdates = () => { ... } - REMOVED
        
        // Track user activity
        const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart']
        const updateUserActivity = () => dispatch(updateActivity())
        
        activityEvents.forEach(event => {
          document.addEventListener(event, updateUserActivity, true)
        })

        setInitializing(false)

        return () => {
          activityEvents.forEach(event => {
            document.removeEventListener(event, updateUserActivity, true)
          })
          
          // Stop sensor data service
          sensorDataService.stop()
          unsubscribeSensorData()
          
          // Disconnect WebSocket
          webSocketService.disconnect()
        }
      } catch (error) {
        console.error('Failed to initialize app:', error)
        dispatch(setConnectionStatus('error'))
        dispatch(addNotification({
          type: 'error',
          title: 'Initialization Error',
          message: 'Failed to initialize application'
        }))
        setInitializing(false)
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
        sx={{ backgroundColor: 'background.default' }}
      >
        <Logo size={80} showText={true} />
        <CircularProgress size={48} thickness={4} />
        <Box textAlign="center">
          <Typography variant="h6" color="primary" gutterBottom>
            Initializing LawnBerryPi Control...
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Connecting to mower system
          </Typography>
        </Box>
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

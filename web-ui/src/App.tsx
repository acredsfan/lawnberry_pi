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
import { usePerformanceMonitor } from './hooks/usePerformanceMonitor'

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

        // Simulate periodic data updates for demo purposes
        const simulateDataUpdates = () => {
          setInterval(() => {
            const updatedStatus = {
              ...mockMowerStatus,
              battery: {
                ...mockMowerStatus.battery,
                level: Math.max(20, mockMowerStatus.battery.level - Math.random() * 0.5),
                current: 1.5 + Math.random() * 0.6
              },
              sensors: {
                ...mockMowerStatus.sensors,
                environmental: {
                  ...mockMowerStatus.sensors.environmental,
                  temperature: 24.5 + (Math.random() - 0.5) * 2,
                  humidity: 65 + (Math.random() - 0.5) * 10
                },
                imu: {
                  ...mockMowerStatus.sensors.imu,
                  acceleration: {
                    x: (Math.random() - 0.5) * 0.2,
                    y: (Math.random() - 0.5) * 0.2,
                    z: 9.81 + (Math.random() - 0.5) * 0.1
                  }
                }
              },
              coverage: {
                ...mockMowerStatus.coverage,
                coveredArea: Math.min(1000, mockMowerStatus.coverage.coveredArea + Math.random() * 5),
                percentage: Math.min(100, mockMowerStatus.coverage.percentage + Math.random() * 0.5)
              },
              lastUpdate: Date.now()
            }
            dispatch(setStatus(updatedStatus))
          }, 3000) // Update every 3 seconds for demo
        }

        // Start data simulation after a short delay
        setTimeout(simulateDataUpdates, 2000)

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

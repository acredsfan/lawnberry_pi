import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
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
import Logo from './components/Logo'
import { webSocketService } from './services/websocket'
import { usePerformanceMonitor } from './hooks/usePerformanceMonitor'

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

        webSocketService.on('mower_status', (data) => {
          dispatch(setStatus(data))
        })

        webSocketService.on('weather_data', (data) => {
          dispatch(setWeatherData(data))
        })

        webSocketService.on('notification', (data) => {
          dispatch(addNotification(data))
        })

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
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/navigation" element={<Navigation />} />
          <Route path="/maps" element={<Maps />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/training" element={<Training />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>

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

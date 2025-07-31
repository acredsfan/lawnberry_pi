import React from 'react'
import { Box, Typography, Chip } from '@mui/material'
import { Wifi as WifiIcon, WifiOff as WifiOffIcon, Error as ErrorIcon } from '@mui/icons-material'
import { useSelector } from 'react-redux'
import { RootState } from '../../store/store'

const ConnectionStatus: React.FC = () => {
  const { connectionStatus, performanceMetrics } = useSelector((state: RootState) => state.ui)
  const { isConnected } = useSelector((state: RootState) => state.mower)

  const getStatusConfig = () => {
    switch (connectionStatus) {
      case 'connected':
        return {
          color: 'success' as const,
          icon: <WifiIcon fontSize="small" />,
          label: 'Connected',
          description: 'System online'
        }
      case 'connecting':
        return {
          color: 'warning' as const,
          icon: <WifiIcon fontSize="small" />,
          label: 'Connecting',
          description: 'Establishing connection'
        }
      case 'disconnected':
        return {
          color: 'default' as const,
          icon: <WifiOffIcon fontSize="small" />,
          label: 'Disconnected',
          description: 'System offline'
        }
      case 'error':
        return {
          color: 'error' as const,
          icon: <ErrorIcon fontSize="small" />,
          label: 'Error',
          description: 'Connection failed'
        }
      default:
        return {
          color: 'default' as const,
          icon: <WifiOffIcon fontSize="small" />,
          label: 'Unknown',
          description: 'Status unknown'
        }
    }
  }

  const statusConfig = getStatusConfig()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Chip
        icon={statusConfig.icon}
        label={statusConfig.label}
        color={statusConfig.color}
        size="small"
        variant="outlined"
      />
      
      <Typography variant="caption" color="text.secondary">
        {statusConfig.description}
      </Typography>

      {connectionStatus === 'connected' && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Latency: {performanceMetrics.networkLatency}ms
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Memory: {performanceMetrics.memoryUsage.toFixed(1)}MB
          </Typography>
        </Box>
      )}
    </Box>
  )
}

export default ConnectionStatus

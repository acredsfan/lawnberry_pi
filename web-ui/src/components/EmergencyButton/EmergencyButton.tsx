import React from 'react'
import { Button, ButtonProps } from '@mui/material'
import { Stop as StopIcon } from '@mui/icons-material'

interface EmergencyButtonProps extends Omit<ButtonProps, 'onClick'> {
  onClick: () => void
  active?: boolean
}

const EmergencyButton: React.FC<EmergencyButtonProps> = ({ 
  onClick, 
  active = false, 
  sx, 
  ...props 
}) => {
  return (
    <Button
      variant="contained"
      color="error"
      onClick={onClick}
      startIcon={<StopIcon />}
      className="emergency-stop"
      sx={{
        minWidth: 120,
        fontWeight: 'bold',
        backgroundColor: active ? '#b71c1c' : '#d32f2f',
        '&:hover': {
          backgroundColor: '#b71c1c',
        },
        animation: active ? 'pulse 1s infinite' : 'none',
        '@keyframes pulse': {
          '0%': {
            boxShadow: '0 0 0 0 rgba(211, 47, 47, 0.7)',
          },
          '70%': {
            boxShadow: '0 0 0 10px rgba(211, 47, 47, 0)',
          },
          '100%': {
            boxShadow: '0 0 0 0 rgba(211, 47, 47, 0)',
          },
        },
        ...sx
      }}
      {...props}
    >
      {active ? 'STOPPED' : 'EMERGENCY'}
    </Button>
  )
}

export default EmergencyButton

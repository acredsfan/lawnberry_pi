import React from 'react'
import { Box, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'

interface LogoProps {
  size?: number
  showText?: boolean
}

const Logo: React.FC<LogoProps> = ({ size = 40, showText = true }) => {
  const navigate = useNavigate()

  const handleClick = () => {
    navigate('/dashboard')
  }

  return (
    <Box
      onClick={handleClick}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        cursor: 'pointer',
        '&:hover': {
          opacity: 0.8,
        }
      }}
    >
      <Box
        component="img"
        src="/assets/LawnBerryPi_logo.png"
        alt="LawnBerryPi Logo"
        sx={{
          width: size,
          height: size,
          objectFit: 'contain',
        }}
      />
      {showText && (
        <Typography
          variant="h6"
          sx={{
            fontWeight: 600,
            color: 'primary.main',
          }}
        >
          LawnBerryPi
        </Typography>
      )}
    </Box>
  )
}

export default Logo

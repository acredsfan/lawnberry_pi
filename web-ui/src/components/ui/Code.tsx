import React from 'react'
import { Box, SxProps, Theme } from '@mui/material'

interface CodeProps {
  children: React.ReactNode
  sx?: SxProps<Theme>
  inline?: boolean
}

const Code: React.FC<CodeProps> = ({ children, sx, inline = false }) => {
  const baseStyles: SxProps<Theme> = {
    fontFamily: '"Fira Code", "Consolas", "Monaco", "Courier New", monospace',
    fontSize: inline ? '0.875rem' : '0.8rem',
    backgroundColor: '#f5f5f5',
    border: '1px solid #e0e0e0',
    color: '#2E7D32', // LawnBerry Pi primary green
    fontWeight: 500,
    ...(inline ? {
      padding: '2px 6px',
      borderRadius: '4px',
      display: 'inline-block',
    } : {
      padding: '12px 16px',
      borderRadius: '8px',
      display: 'block',
      whiteSpace: 'pre-wrap',
      overflowX: 'auto',
    }),
    ...sx,
  }

  return (
    <Box component={inline ? 'code' : 'pre'} sx={baseStyles}>
      {children}
    </Box>
  )
}

export default Code

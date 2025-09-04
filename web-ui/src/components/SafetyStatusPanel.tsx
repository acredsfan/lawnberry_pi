import React, { useEffect, useState } from 'react'
import { Card, CardContent, Typography } from '@mui/material'
import { webSocketService } from '../services/websocket'

export default function SafetyStatusPanel() {
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    const h = (payload: any) => setData(payload && typeof payload === 'object' && 'data' in payload ? (payload as any).data : payload)
    try { webSocketService.on('safety/status', h) } catch {}
    try { webSocketService.subscribe('safety/status') } catch {}
    return () => {
      try { webSocketService.off('safety/status', h) } catch {}
      try { webSocketService.unsubscribe('safety/status') } catch {}
    }
  }, [])
  return (
    <Card className="holographic" sx={{ height: 450 }}>
      <CardContent>
        <Typography variant="h6" className="neon-text" sx={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Safety Status
        </Typography>
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
          {data ? JSON.stringify(data, null, 2) : 'Waiting for safety/status...'}
        </pre>
      </CardContent>
    </Card>
  )
}

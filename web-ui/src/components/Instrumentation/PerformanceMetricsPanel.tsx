import React, { useEffect, useState } from 'react'
import { Card, CardContent, Typography, Box, Chip, Button, Tooltip, Grid } from '@mui/material'
import { perfMetrics, PerfMetricsSnapshot } from '../../utils/perfMetrics'

const PerformanceMetricsPanel: React.FC = () => {
  const [snapshot, setSnapshot] = useState<PerfMetricsSnapshot | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const refresh = () => {
    const snap = perfMetrics.exportSnapshot()
    setSnapshot(snap)
  }

  useEffect(() => {
    refresh()
    if (autoRefresh) {
      const interval = setInterval(refresh, 5000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh])

  const latencyChip = (label: string, ms?: number) => (
    <Chip
      key={label}
      label={`${label}: ${ms != null ? ms.toFixed(0) + 'ms' : '—'}`}
      color={ms == null ? 'default' : ms < 800 ? 'success' : ms < 1600 ? 'warning' : 'error'}
      size="small"
      sx={{ mr: 1, mb: 1 }}
    />
  )

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">Performance Metrics</Typography>
          <Box display="flex" gap={1}>
            <Button size="small" variant="outlined" onClick={refresh}>Refresh</Button>
            <Button size="small" variant={autoRefresh ? 'contained' : 'outlined'} onClick={() => setAutoRefresh(a => !a)}>
              {autoRefresh ? 'Auto:On' : 'Auto:Off'}
            </Button>
          </Box>
        </Box>
        {snapshot && (
          <>
            <Box mb={2}>
              {latencyChip('Hydration', snapshot.hydrationDurationMs)}
              {latencyChip('WS Connect', snapshot.webSocketConnectDurationMs)}
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2">Custom Marks</Typography>
                <Box display="flex" flexWrap="wrap" mt={1}>
                  {Object.entries(snapshot.customMarks).map(([k, v]) => (
                    <Tooltip key={k} title={v.toFixed(2)+ ' ms since nav start'}>
                      <Chip label={k} size="small" sx={{ mr: 1, mb: 1 }} />
                    </Tooltip>
                  ))}
                  {Object.keys(snapshot.customMarks).length === 0 && (
                    <Typography variant="caption" color="text.secondary">No marks recorded</Typography>
                  )}
                </Box>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2">Raw Timestamps</Typography>
                <Typography variant="caption" component="pre" style={{ whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(snapshot, null, 2)}
                </Typography>
              </Grid>
            </Grid>
          </>
        )}
      </CardContent>
    </Card>
  )
}

export default PerformanceMetricsPanel

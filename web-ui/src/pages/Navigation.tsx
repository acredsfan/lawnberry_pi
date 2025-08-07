import React, { useEffect, useRef, useState } from 'react'
import { Box, Card, CardContent, Typography, Grid, Button, FormControl, InputLabel, Select, MenuItem, Chip, IconButton, Switch, FormControlLabel } from '@mui/material'
import { PlayArrow, Stop, MyLocation, Layers } from '@mui/icons-material'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '../store/store'
import { setCurrentPattern, addCommand } from '../store/slices/mowerSlice'
import { setMapCenter, setMapZoom, toggleCoverage, toggleObstacles, togglePath } from '../store/slices/navigationSlice'
import { Loader } from '@googlemaps/js-api-loader'

const Navigation: React.FC = () => {
  const dispatch = useDispatch()
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<google.maps.Map | null>(null)
  const [isMapLoaded, setIsMapLoaded] = useState(false)
  
  const { status, patterns, currentPattern, boundaries } = useSelector((state: RootState) => state.mower)
  const { currentPath, plannedPath, obstacles, coverage, showCoverage, showObstacles, showPath, mapCenter, mapZoom } = useSelector((state: RootState) => state.navigation)

  useEffect(() => {
    const initializeMap = async () => {
      if (!mapRef.current) return

      try {
        const loader = new Loader({
          apiKey: process.env.REACT_APP_GOOGLE_MAPS_API_KEY || 'YOUR_API_KEY_HERE',
          version: 'weekly',
          libraries: ['geometry', 'drawing']
        })

        const google = await loader.load()
        
        const initialCenter = mapCenter || status?.position || { lat: 40.0, lng: -82.0 }
        
        const map = new google.maps.Map(mapRef.current, {
          center: initialCenter,
          zoom: mapZoom,
          mapTypeId: google.maps.MapTypeId.SATELLITE,
          disableDefaultUI: false,
          zoomControl: true,
          mapTypeControl: true,
          scaleControl: true,
          streetViewControl: false,
          rotateControl: true,
          fullscreenControl: true,
        })

        mapInstanceRef.current = map

        // Add event listeners
        map.addListener('center_changed', () => {
          const center = map.getCenter()
          if (center) {
            dispatch(setMapCenter({ lat: center.lat(), lng: center.lng() }))
          }
        })

        map.addListener('zoom_changed', () => {
          dispatch(setMapZoom(map.getZoom() || 18))
        })

        setIsMapLoaded(true)
      } catch (error) {
        console.error('Failed to load Google Maps:', error)
      }
    }

    initializeMap()
  }, [dispatch, mapCenter, mapZoom, status?.position])

  useEffect(() => {
    if (!mapInstanceRef.current || !isMapLoaded) return

    const map = mapInstanceRef.current

    // Clear existing overlays
    // In a real implementation, you'd track and remove existing overlays

    // Draw boundaries
    boundaries.forEach(boundary => {
      if (boundary.type === 'boundary') {
        const polygon = new google.maps.Polygon({
          paths: boundary.coordinates,
          strokeColor: '#4CAF50',
          strokeOpacity: 0.8,
          strokeWeight: 2,
          fillColor: '#4CAF50',
          fillOpacity: 0.1,
        })
        polygon.setMap(map)
      } else if (boundary.type === 'no-go') {
        const polygon = new google.maps.Polygon({
          paths: boundary.coordinates,
          strokeColor: '#F44336',
          strokeOpacity: 0.8,
          strokeWeight: 2,
          fillColor: '#F44336',
          fillOpacity: 0.3,
        })
        polygon.setMap(map)
      } else if (boundary.type === 'home') {
        const marker = new google.maps.Marker({
          position: boundary.coordinates[0],
          map: map,
          icon: {
            url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(`
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M10 20V14H14V20H19V12H22L12 3L2 12H5V20H10Z" fill="#4CAF50"/>
              </svg>
            `),
            scaledSize: new google.maps.Size(32, 32),
          },
          title: 'Home Position'
        })
      }
    })

    // Draw current position
    if (status?.position) {
      const marker = new google.maps.Marker({
        position: { lat: status.position.lat, lng: status.position.lng },
        map: map,
        icon: {
          url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(`
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="8" fill="#2196F3"/>
              <circle cx="12" cy="12" r="3" fill="white"/>
            </svg>
          `),
          scaledSize: new google.maps.Size(24, 24),
          anchor: new google.maps.Point(12, 12),
        },
        title: 'Current Position'
      })
    }

    // Draw current path
    if (showPath && currentPath.length > 1) {
      const pathLine = new google.maps.Polyline({
        path: currentPath,
        geodesic: true,
        strokeColor: '#FF9800',
        strokeOpacity: 1.0,
        strokeWeight: 3,
      })
      pathLine.setMap(map)
    }

    // Draw planned path
    if (showPath && plannedPath.length > 1) {
      const plannedLine = new google.maps.Polyline({
        path: plannedPath,
        geodesic: true,
        strokeColor: '#9C27B0',
        strokeOpacity: 0.7,
        strokeWeight: 2,
      })
      plannedLine.setMap(map)
    }

    // Draw obstacles
    if (showObstacles) {
      obstacles.forEach(obstacle => {
        const marker = new google.maps.Marker({
          position: obstacle.position,
          map: map,
          icon: {
            url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(`
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L13.09 8.26L22 12L13.09 15.74L12 22L10.91 15.74L2 12L10.91 8.26L12 2Z" fill="#F44336"/>
              </svg>
            `),
            scaledSize: new google.maps.Size(20, 20),
          },
          title: `${obstacle.type} (${(obstacle.confidence * 100).toFixed(0)}%)`
        })
      })
    }

    // Draw coverage
    if (showCoverage) {
      coverage.forEach(point => {
        const circle = new google.maps.Circle({
          strokeColor: point.covered ? '#4CAF50' : '#FFC107',
          strokeOpacity: 0.3,
          strokeWeight: 1,
          fillColor: point.covered ? '#4CAF50' : '#FFC107',
          fillOpacity: 0.2,
          map: map,
          center: { lat: point.lat, lng: point.lng },
          radius: 0.5, // 0.5 meter radius
        })
      })
    }
  }, [boundaries, status?.position, currentPath, plannedPath, obstacles, coverage, showCoverage, showObstacles, showPath, isMapLoaded])

  const handleStartMowing = () => {
    if (!currentPattern) {
      alert('Please select a mowing pattern first')
      return
    }
    dispatch(addCommand({ command: `start_mowing:${currentPattern}` }))
  }

  const handleStopMowing = () => {
    dispatch(addCommand({ command: 'stop_mowing' }))
  }

  const handleCenterOnMower = () => {
    if (status?.position && mapInstanceRef.current) {
      mapInstanceRef.current.setCenter(status.position)
      mapInstanceRef.current.setZoom(20)
    }
  }

  const getStatusColor = (state: string) => {
    switch (state) {
      case 'mowing': return 'success'
      case 'charging': return 'info' 
      case 'returning': return 'warning'
      case 'error': return 'error'
      case 'emergency': return 'error'
      default: return 'default'
    }
  }

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Mowing Control</Typography>
                <Box display="flex" gap={1}>
                  <FormControl size="small" sx={{ minWidth: 160 }}>
                    <InputLabel>Pattern</InputLabel>
                    <Select
                      value={currentPattern || ''}
                      label="Pattern"
                      onChange={(e) => dispatch(setCurrentPattern(e.target.value))}
                    >
                      {patterns.map((pattern) => (
                        <MenuItem key={pattern.id} value={pattern.id}>
                          {pattern.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  
                  <Button
                    variant="contained"
                    startIcon={<PlayArrow />}
                    onClick={handleStartMowing}
                    disabled={status?.state === 'mowing'}
                    color="success"
                  >
                    Start
                  </Button>
                  
                  <Button
                    variant="outlined"
                    startIcon={<Stop />}
                    onClick={handleStopMowing}
                    disabled={status?.state !== 'mowing'}
                    color="error"
                  >
                    Stop
                  </Button>
                </Box>
              </Box>
              
              <Box display="flex" alignItems="center" gap={2}>
                <Chip 
                  label={status?.state?.toUpperCase() || 'IDLE'} 
                  color={getStatusColor(status?.state || 'idle')}
                  size="small"
                />
                <Typography variant="body2" color="text.secondary">
                  Coverage: {status?.coverage?.percentage.toFixed(1) || '0'}%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Battery: {status?.battery.level ? status.battery.level.toFixed(1) : '0.0'}%
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Map Controls</Typography>
              <Box display="flex" flexDirection="column" gap={1}>
                <FormControlLabel
                  control={<Switch checked={showPath} onChange={() => dispatch(togglePath())} />}
                  label="Show Path"
                />
                <FormControlLabel
                  control={<Switch checked={showObstacles} onChange={() => dispatch(toggleObstacles())} />}
                  label="Show Obstacles"
                />
                <FormControlLabel
                  control={<Switch checked={showCoverage} onChange={() => dispatch(toggleCoverage())} />}
                  label="Show Coverage"
                />
                <Button
                  startIcon={<MyLocation />}
                  onClick={handleCenterOnMower}
                  size="small"
                  disabled={!status?.position}
                >
                  Center on Mower
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card sx={{ flexGrow: 1, minHeight: 400 }}>
        <CardContent sx={{ height: '100%', p: 0 }}>
          <div 
            ref={mapRef} 
            className="map-container"
            style={{ height: '100%', width: '100%' }}
          />
          {!isMapLoaded && (
            <Box 
              display="flex" 
              justifyContent="center" 
              alignItems="center" 
              height="100%"
              position="absolute"
              top={0}
              left={0}
              right={0}
              bottom={0}
              bgcolor="rgba(0,0,0,0.1)"
            >
              <Typography>Loading map...</Typography>
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
  )
}

export default Navigation

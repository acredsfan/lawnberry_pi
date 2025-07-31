import React, { useState } from 'react'
import {
  Box,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  Grid,
  List,
  ListItem,
  ListItemText,
  Button,
  TextField,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  FormControl,
  InputLabel,
  Select,
  MenuItem
} from '@mui/material'
import {
  ExpandMore as ExpandMoreIcon,
  Api as ApiIcon,
  Architecture as ArchitectureIcon,
  Code as CodeIcon,
  Settings as ConfigIcon,
  BugReport as ErrorIcon,
  Speed as PerformanceIcon,
  Security as SecurityIcon,
  Extension as PluginIcon,
  PlayArrow as TestIcon,
  Close as CloseIcon,
  ContentCopy as CopyIcon
} from '@mui/icons-material'

interface TechnicalReferenceProps {
  expertiseLevel: 'basic' | 'advanced' | 'technician'
}

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`technical-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 2 }}>{children}</Box>}
    </div>
  )
}

const TechnicalReference: React.FC<TechnicalReferenceProps> = ({ expertiseLevel }) => {
  const [activeTab, setActiveTab] = useState(0)
  const [apiTestOpen, setApiTestOpen] = useState(false)
  const [selectedEndpoint, setSelectedEndpoint] = useState('')
  const [testMethod, setTestMethod] = useState('GET')
  const [testUrl, setTestUrl] = useState('')
  const [testBody, setTestBody] = useState('')
  const [testResponse, setTestResponse] = useState('')

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue)
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  const testEndpoint = async () => {
    try {
      const response = await fetch(testUrl, {
        method: testMethod,
        headers: {
          'Content-Type': 'application/json',
        },
        body: testMethod !== 'GET' ? testBody : undefined,
      })
      const data = await response.json()
      setTestResponse(JSON.stringify(data, null, 2))
    } catch (error) {
      setTestResponse(`Error: ${error}`)
    }
  }

  const apiEndpoints = [
    {
      category: 'System',
      endpoints: [
        {
          path: '/api/v1/system/status',
          method: 'GET',
          description: 'Get overall system status and health',
          response: {
            status: 'operational',
            services: {
              communication: 'running',
              hardware: 'running',
              safety: 'running',
              weather: 'running',
              power: 'running',
              sensor_fusion: 'running',
              vision: 'running',
              web_api: 'running',
              data_management: 'running',
              system_integration: 'running',
              location: 'running'
            },
            uptime: 86400,
            version: '2.0.0'
          }
        },
        {
          path: '/api/v1/system/config',
          method: 'GET',
          description: 'Get system configuration',
          response: {
            hardware: {
              sensors: ['tof_left', 'tof_right', 'bme280', 'ina3221'],
              gpio_pins: {
                tof_left_shutdown: 22,
                tof_right_shutdown: 23
              }
            }
          }
        }
      ]
    },
    {
      category: 'Navigation',
      endpoints: [
        {
          path: '/api/v1/navigation/start',
          method: 'POST',
          description: 'Start mowing operation',
          body: {
            pattern: 'parallel',
            area: 'main_yard',
            speed: 'normal'
          },
          response: {
            status: 'started',
            session_id: 'uuid-string',
            estimated_duration: 3600
          }
        },
        {
          path: '/api/v1/navigation/stop',
          method: 'POST',
          description: 'Stop current mowing operation',
          response: {
            status: 'stopped',
            reason: 'user_request'
          }
        },
        {
          path: '/api/v1/navigation/status',
          method: 'GET',
          description: 'Get current navigation status',
          response: {
            state: 'mowing',
            position: { lat: 40.7128, lng: -74.0060 },
            battery_level: 75,
            coverage_percent: 45
          }
        }
      ]
    },
    {
      category: 'Maps',
      endpoints: [
        {
          path: '/api/v1/maps/boundaries',
          method: 'GET',
          description: 'Get yard boundaries',
          response: {
            boundaries: [
              { lat: 40.7128, lng: -74.0060 },
              { lat: 40.7129, lng: -74.0061 }
            ]
          }
        },
        {
          path: '/api/v1/maps/boundaries',
          method: 'POST',
          description: 'Set yard boundaries',
          body: {
            boundaries: [
              { lat: 40.7128, lng: -74.0060 },
              { lat: 40.7129, lng: -74.0061 }
            ]
          }
        },
        {
          path: '/api/v1/maps/no-go-zones',
          method: 'GET',
          description: 'Get no-go zones',
          response: {
            zones: [
              {
                center: { lat: 40.7128, lng: -74.0060 },
                radius: 5
              }
            ]
          }
        }
      ]
    },
    {
      category: 'Sensors',
      endpoints: [
        {
          path: '/api/v1/sensors/data',
          method: 'GET',
          description: 'Get latest sensor readings',
          response: {
            tof_left: { distance: 150, confidence: 95 },
            tof_right: { distance: 200, confidence: 98 },
            imu: {
              acceleration: { x: 0.1, y: 0.2, z: 9.8 },
              gyroscope: { x: 0.0, y: 0.0, z: 0.0 }
            },
            environmental: {
              temperature: 22.5,
              humidity: 65,
              pressure: 1013.25
            }
          }
        }
      ]
    },
    {
      category: 'Power',
      endpoints: [
        {
          path: '/api/v1/power/status',
          method: 'GET',
          description: 'Get power system status',
          response: {
            battery: {
              voltage: 12.6,
              current: -2.5,
              level: 85,
              temperature: 25
            },
            solar: {
              voltage: 18.2,
              current: 1.8,
              power: 32.8
            },
            charging: true
          }
        }
      ]
    }
  ]

  const microservices = [
    {
      name: 'Communication Service',
      description: 'MQTT-based inter-service messaging',
      port: 1883,
      endpoints: ['MQTT broker'],
      dependencies: ['Redis'],
      config: {
        broker_host: 'localhost',
        broker_port: 1883,
        topics: ['sensors/*', 'navigation/*', 'safety/*']
      }
    },
    {
      name: 'Hardware Interface Service',
      description: 'Direct hardware communication and abstraction',
      port: 8001,
      endpoints: ['/hardware/sensors', '/hardware/actuators'],
      dependencies: ['I2C', 'GPIO', 'UART'],
      config: {
        i2c_bus: 1,
        gpio_base: '/sys/class/gpio',
        uart_devices: ['/dev/ttyACM0', '/dev/ttyACM1']
      }
    },
    {
      name: 'Safety Service',
      description: 'Comprehensive safety monitoring and emergency response',
      port: 8002,
      endpoints: ['/safety/status', '/safety/emergency'],
      dependencies: ['Sensor Fusion Service'],
      config: {
        emergency_timeout: 100,
        obstacle_threshold: 30,
        slope_limit: 15
      }
    },
    {
      name: 'Weather Service',
      description: 'Weather data integration and forecasting',
      port: 8003,
      endpoints: ['/weather/current', '/weather/forecast'],
      dependencies: ['OpenWeather API'],
      config: {
        api_key: 'your_openweather_key',
        update_interval: 300,
        location: { lat: 40.7128, lng: -74.0060 }
      }
    }
  ]

  const errorCodes = [
    { code: 'E001', category: 'Hardware', description: 'Sensor communication failure', resolution: 'Check I2C connections' },
    { code: 'E002', category: 'Safety', description: 'Emergency stop activated', resolution: 'Check for obstacles and reset' },
    { code: 'E003', category: 'Navigation', description: 'GPS signal lost', resolution: 'Move to open area for better reception' },
    { code: 'E004', category: 'Power', description: 'Low battery warning', resolution: 'Return to charging station' },
    { code: 'E005', category: 'Vision', description: 'Camera initialization failed', resolution: 'Check camera connection and permissions' }
  ]

  const pluginAPI = {
    hooks: [
      {
        name: 'on_mowing_start',
        description: 'Called when mowing operation begins',
        parameters: ['session_data'],
        example: `
def on_mowing_start(session_data):
    print(f"Starting mowing session: {session_data['id']}")
    # Custom initialization logic here
    return True
        `
      },
      {
        name: 'on_obstacle_detected',
        description: 'Called when obstacle is detected',
        parameters: ['obstacle_data', 'sensor_data'],
        example: `
def on_obstacle_detected(obstacle_data, sensor_data):
    # Custom obstacle handling logic
    if obstacle_data['confidence'] > 0.8:
        return 'stop'  # Stop immediately
    return 'continue'  # Continue with default behavior
        `
      }
    ],
    api_functions: [
      {
        name: 'get_sensor_data(sensor_type)',
        description: 'Get current sensor readings',
        returns: 'dict with sensor data'
      },
      {
        name: 'send_command(command, parameters)',
        description: 'Send command to navigation system',
        returns: 'command execution status'
      },
      {
        name: 'log_event(level, message)',
        description: 'Log plugin events',
        returns: 'None'
      }
    ]
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Technical Reference - Developer Documentation
      </Typography>

      <Tabs value={activeTab} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
        <Tab icon={<ApiIcon />} label="API Reference" />
        <Tab icon={<ArchitectureIcon />} label="Architecture" />
        <Tab icon={<ConfigIcon />} label="Configuration" />
        <Tab icon={<ErrorIcon />} label="Error Codes" />
        <Tab icon={<PluginIcon />} label="Plugin API" />
        <Tab icon={<PerformanceIcon />} label="Performance" />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Typography variant="h6" gutterBottom>REST API Endpoints</Typography>
        
        <Button 
          variant="contained" 
          startIcon={<TestIcon />}
          onClick={() => setApiTestOpen(true)}
          sx={{ mb: 3 }}
        >
          Open API Tester
        </Button>

        {apiEndpoints.map((category, categoryIndex) => (
          <Accordion key={categoryIndex} defaultExpanded={categoryIndex === 0}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="h6">{category.category} API</Typography>
            </AccordionSummary>
            <AccordionDetails>
              {category.endpoints.map((endpoint, endpointIndex) => (
                <Card key={endpointIndex} sx={{ mb: 2 }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <Chip 
                        label={endpoint.method} 
                        color={endpoint.method === 'GET' ? 'primary' : 'secondary'}
                        size="small"
                        sx={{ mr: 1 }}
                      />
                      <Typography variant="subtitle1" sx={{ fontFamily: 'monospace' }}>
                        {endpoint.path}
                      </Typography>
                      <IconButton 
                        size="small"
                        onClick={() => copyToClipboard(endpoint.path)}
                        sx={{ ml: 1 }}
                      >
                        <CopyIcon fontSize="small" />
                      </IconButton>
                    </Box>
                    
                    <Typography variant="body2" color="textSecondary" gutterBottom>
                      {endpoint.description}
                    </Typography>

                    {endpoint.body && (
                      <Box sx={{ mt: 2 }}>
                        <Typography variant="subtitle2">Request Body:</Typography>
                        <Paper sx={{ p: 1, backgroundColor: '#f5f5f5', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                          <pre>{JSON.stringify(endpoint.body, null, 2)}</pre>
                        </Paper>
                      </Box>
                    )}

                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2">Response:</Typography>
                      <Paper sx={{ p: 1, backgroundColor: '#f5f5f5', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        <pre>{JSON.stringify(endpoint.response, null, 2)}</pre>
                      </Paper>
                    </Box>

                    <Button
                      size="small"
                      onClick={() => {
                        setSelectedEndpoint(endpoint.path)
                        setTestMethod(endpoint.method)
                        setTestUrl(`http://localhost:8080${endpoint.path}`)
                        setTestBody(endpoint.body ? JSON.stringify(endpoint.body, null, 2) : '')
                        setApiTestOpen(true)
                      }}
                      sx={{ mt: 1 }}
                    >
                      Test Endpoint
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </AccordionDetails>
          </Accordion>
        ))}
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Typography variant="h6" gutterBottom>System Architecture</Typography>
        
        <Alert severity="info" sx={{ mb: 3 }}>
          LawnBerryPi uses a microservices architecture with 11 independent services communicating via MQTT.
        </Alert>

        <Grid container spacing={3}>
          {microservices.map((service, index) => (
            <Grid item xs={12} md={6} key={index}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {service.name}
                  </Typography>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    {service.description}
                  </Typography>
                  
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2">Port: {service.port}</Typography>
                    <Typography variant="subtitle2">Dependencies:</Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 1 }}>
                      {service.dependencies.map((dep, depIndex) => (
                        <Chip key={depIndex} label={dep} size="small" />
                      ))}
                    </Box>
                  </Box>

                  <Accordion sx={{ mt: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="body2">Configuration</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Paper sx={{ p: 1, backgroundColor: '#f5f5f5', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        <pre>{JSON.stringify(service.config, null, 2)}</pre>
                      </Paper>
                    </AccordionDetails>
                  </Accordion>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Typography variant="h6" gutterBottom>Configuration Files</Typography>
        
        <Typography variant="body1" gutterBottom>
          System configuration is managed through YAML files in the <code>/config</code> directory.
        </Typography>

        <Grid container spacing={2}>
          {[
            'system.yaml', 'hardware.yaml', 'safety.yaml', 'communication.yaml',
            'power_management.yaml', 'vision.yaml', 'sensor_fusion.yaml'
          ].map((file, index) => (
            <Grid item xs={12} sm={6} md={4} key={index}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle1">{file}</Typography>
                  <Typography variant="body2" color="textSecondary">
                    Configuration for {file.replace('.yaml', '').replace('_', ' ')} system
                  </Typography>
                  <Button size="small" sx={{ mt: 1 }}>
                    View Config
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Typography variant="h6" gutterBottom>Error Codes Reference</Typography>
        
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Description</TableCell>
                <TableCell>Resolution</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {errorCodes.map((error, index) => (
                <TableRow key={index}>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    <Chip label={error.code} size="small" />
                  </TableCell>
                  <TableCell>{error.category}</TableCell>
                  <TableCell>{error.description}</TableCell>
                  <TableCell>{error.resolution}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </TabPanel>

      <TabPanel value={activeTab} index={4}>
        <Typography variant="h6" gutterBottom>Plugin Development API</Typography>
        
        <Typography variant="body1" gutterBottom>
          Extend LawnBerryPi functionality with custom plugins using the plugin API framework.
        </Typography>

        <Accordion defaultExpanded>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="h6">Event Hooks</Typography>
          </AccordionSummary>
          <AccordionDetails>
            {pluginAPI.hooks.map((hook, index) => (
              <Card key={index} sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontFamily: 'monospace' }}>
                    {hook.name}
                  </Typography>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    {hook.description}
                  </Typography>
                  <Typography variant="body2">
                    Parameters: {hook.parameters.join(', ')}
                  </Typography>
                  <Paper sx={{ mt: 2, p: 1, backgroundColor: '#f5f5f5' }}>
                    <pre style={{ fontSize: '0.8rem' }}>{hook.example}</pre>
                  </Paper>
                </CardContent>
              </Card>
            ))}
          </AccordionDetails>
        </Accordion>

        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="h6">API Functions</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <List>
              {pluginAPI.api_functions.map((func, index) => (
                <ListItem key={index}>
                  <ListItemText
                    primary={func.name}
                    secondary={`${func.description} - Returns: ${func.returns}`}
                    primaryTypographyProps={{ fontFamily: 'monospace' }}
                  />
                </ListItem>
              ))}
            </List>
          </AccordionDetails>
        </Accordion>
      </TabPanel>

      <TabPanel value={activeTab} index={5}>
        <Typography variant="h6" gutterBottom>Performance Tuning Guide</Typography>
        
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <PerformanceIcon sx={{ mr: 1 }} />
                  CPU Optimization
                </Typography>
                <List>
                  <ListItem>
                    <ListItemText 
                      primary="Service Priority"
                      secondary="Safety service has highest priority, followed by hardware interface"
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="CPU Affinity"
                      secondary="Distribute services across available CPU cores"
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="Async I/O"
                      secondary="All services use asyncio for non-blocking operations"
                    />
                  </ListItem>
                </List>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <PerformanceIcon sx={{ mr: 1 }} />
                  Memory Management
                </Typography>
                <List>
                  <ListItem>
                    <ListItemText 
                      primary="Redis Caching"
                      secondary="Intelligent caching reduces memory pressure"
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="Memory Pools"
                      secondary="Computer vision uses memory pooling for efficiency"
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="Garbage Collection"
                      secondary="Optimized GC settings for real-time performance"
                    />
                  </ListItem>
                </List>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* API Tester Dialog */}
      <Dialog open={apiTestOpen} onClose={() => setApiTestOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          API Endpoint Tester
          <IconButton
            onClick={() => setApiTestOpen(false)}
            sx={{ position: 'absolute', right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={3}>
              <FormControl fullWidth>
                <InputLabel>Method</InputLabel>
                <Select value={testMethod} onChange={(e) => setTestMethod(e.target.value)}>
                  <MenuItem value="GET">GET</MenuItem>
                  <MenuItem value="POST">POST</MenuItem>
                  <MenuItem value="PUT">PUT</MenuItem>
                  <MenuItem value="DELETE">DELETE</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={9}>
              <TextField
                fullWidth
                label="URL"
                value={testUrl}
                onChange={(e) => setTestUrl(e.target.value)}
              />
            </Grid>
            {testMethod !== 'GET' && (
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={4}
                  label="Request Body (JSON)"
                  value={testBody}
                  onChange={(e) => setTestBody(e.target.value)}
                />
              </Grid>
            )}
            <Grid item xs={12}>
              <Button variant="contained" onClick={testEndpoint} sx={{ mr: 1 }}>
                Send Request
              </Button>
            </Grid>
            {testResponse && (
              <Grid item xs={12}>
                <Typography variant="subtitle2">Response:</Typography>
                <Paper sx={{ p: 2, backgroundColor: '#f5f5f5', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                  <pre>{testResponse}</pre>
                </Paper>
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApiTestOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default TechnicalReference

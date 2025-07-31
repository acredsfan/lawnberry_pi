import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Button,
  Checkbox,
  FormControlLabel,
  Alert,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  LinearProgress,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  TextField,
  Tabs,
  Tab
} from '@mui/material'
import {
  Schedule as ScheduleIcon,
  Build as MaintenanceIcon,
  Warning as WarningIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  PlayArrow as TestIcon,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  Upload as UploadIcon,
  ExpandMore as ExpandMoreIcon,
  Close as CloseIcon,
  Notifications as NotificationIcon,
  Calendar as CalendarIcon
} from '@mui/icons-material'

interface MaintenanceGuideProps {
  expertiseLevel: 'basic' | 'advanced' | 'technician'
}

interface MaintenanceTask {
  id: string
  title: string
  frequency: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  estimatedTime: string
  description: string
  steps: string[]
  tools?: string[]
  safetyNotes?: string[]
  completed?: boolean
  lastCompleted?: Date
  nextDue?: Date
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
      id={`maintenance-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 2 }}>{children}</Box>}
    </div>
  )
}

const MaintenanceGuide: React.FC<MaintenanceGuideProps> = ({ expertiseLevel }) => {
  const [activeTab, setActiveTab] = useState(0)
  const [maintenanceTasks, setMaintenanceTasks] = useState<MaintenanceTask[]>([])
  const [selectedTask, setSelectedTask] = useState<MaintenanceTask | null>(null)
  const [taskDialogOpen, setTaskDialogOpen] = useState(false)
  const [diagnosticResults, setDiagnosticResults] = useState<any>(null)
  const [diagnosticRunning, setDiagnosticRunning] = useState(false)

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue)
  }

  const runDiagnostic = async () => {
    setDiagnosticRunning(true)
    // Simulate diagnostic test
    setTimeout(() => {
      setDiagnosticResults({
        overall: 'good',
        tests: [
          { name: 'Hardware Connectivity', status: 'pass', details: 'All sensors responding' },
          { name: 'Service Health', status: 'pass', details: '11/11 services running' },
          { name: 'Database Integrity', status: 'pass', details: 'No corruption detected' },
          { name: 'Network Connectivity', status: 'warning', details: 'Intermittent WiFi signal' },
          { name: 'Storage Space', status: 'pass', details: '15GB available' },
          { name: 'Battery Health', status: 'pass', details: '89% capacity remaining' }
        ]
      })
      setDiagnosticRunning(false)
    }, 3000)
  }

  const getMaintenanceTasksForLevel = (): MaintenanceTask[] => {
    const basicTasks: MaintenanceTask[] = [
      {
        id: 'daily-visual',
        title: 'Daily Visual Inspection',
        frequency: 'Daily',
        priority: 'medium',
        estimatedTime: '5 minutes',
        description: 'Quick visual check of mower condition and surroundings',
        steps: [
          'Check for visible damage to mower body',
          'Ensure blade area is clear of debris',
          'Verify charging station is accessible',
          'Check battery indicator status',
          'Look for any loose connections'
        ],
        safetyNotes: [
          'Always turn off mower before inspection',
          'Never touch blade area with hands'
        ]
      },
      {
        id: 'weekly-cleaning',
        title: 'Weekly Cleaning',
        frequency: 'Weekly',
        priority: 'medium',
        estimatedTime: '15 minutes',
        description: 'Basic cleaning to maintain performance',
        steps: [
          'Turn off mower and disconnect power',
          'Clean camera lens with soft cloth',
          'Remove grass clippings from vents',
          'Wipe down exterior with damp cloth',
          'Check and clean solar panel surface'
        ],
        tools: ['Soft cloth', 'Small brush', 'Compressed air (optional)'],
        safetyNotes: [
          'Ensure mower is completely powered off',
          'Use only damp cloth, never submerge in water'
        ]
      },
      {
        id: 'monthly-battery',
        title: 'Monthly Battery Check',
        frequency: 'Monthly',
        priority: 'high',
        estimatedTime: '10 minutes',
        description: 'Monitor battery health and charging performance',
        steps: [
          'Check battery voltage in web interface',
          'Verify charging current when docked',
          'Clean battery terminals if accessible',
          'Check for any swelling or damage',
          'Review battery performance logs'
        ],
        safetyNotes: [
          'Never attempt to open battery compartment',
          'Contact technician if any abnormalities found'
        ]
      }
    ]

    const advancedTasks: MaintenanceTask[] = [
      ...basicTasks,
      {
        id: 'sensor-calibration',
        title: 'Sensor Calibration',
        frequency: 'Monthly',
        priority: 'high',
        estimatedTime: '30 minutes',
        description: 'Calibrate sensors for optimal performance',
        steps: [
          'Run built-in sensor diagnostic',
          'Calibrate IMU on level surface',
          'Test ToF sensor accuracy',
          'Verify GPS signal strength',
          'Check camera focus and exposure'
        ],
        tools: ['Level surface', 'Measuring tape'],
        safetyNotes: [
          'Perform calibration in open area',
          'Ensure stable network connection'
        ]
      },
      {
        id: 'performance-optimization',
        title: 'Performance Optimization',
        frequency: 'Quarterly',
        priority: 'medium',
        estimatedTime: '45 minutes',
        description: 'Optimize system performance and resource usage',
        steps: [
          'Review system resource usage',
          'Clean up old log files',
          'Optimize database indices',
          'Check service memory usage',
          'Update performance baselines'
        ],
        tools: ['System monitoring tools'],
        safetyNotes: [
          'Backup system before making changes',
          'Monitor system stability after optimization'
        ]
      }
    ]

    const technicianTasks: MaintenanceTask[] = [
      ...advancedTasks,
      {
        id: 'system-backup',
        title: 'Complete System Backup',
        frequency: 'Monthly',
        priority: 'critical',
        estimatedTime: '60 minutes',
        description: 'Full system backup including configuration and data',
        steps: [
          'Stop all non-critical services',
          'Backup configuration files',
          'Export database contents',
          'Create system image backup',
          'Verify backup integrity',
          'Document backup location and restore procedures'
        ],
        tools: ['External storage device', 'Backup software'],
        safetyNotes: [
          'Ensure adequate storage space available',
          'Test restore procedure periodically'
        ]
      },
      {
        id: 'security-audit',
        title: 'Security Audit',
        frequency: 'Quarterly',
        priority: 'high',
        estimatedTime: '90 minutes',
        description: 'Comprehensive security assessment and updates',
        steps: [
          'Review system access logs',
          'Update all software dependencies',
          'Check for security vulnerabilities',
          'Verify firewall configuration',
          'Test backup encryption',
          'Review user access permissions'
        ],
        tools: ['Security scanning tools', 'Log analysis tools'],
        safetyNotes: [
          'Schedule during low-usage periods',
          'Have rollback plan ready'
        ]
      },
      {
        id: 'hardware-diagnostics',
        title: 'Comprehensive Hardware Diagnostics',
        frequency: 'Quarterly',
        priority: 'high',
        estimatedTime: '120 minutes',
        description: 'Deep hardware testing and validation',
        steps: [
          'Run extended memory tests',
          'Test all GPIO pins and connections',
          'Validate sensor accuracy against references',
          'Check power system efficiency',
          'Test emergency shutdown systems',
          'Validate communication interfaces'
        ],
        tools: ['Multimeter', 'Oscilloscope', 'Reference sensors'],
        safetyNotes: [
          'Use proper ESD precautions',
          'Have replacement components available'
        ]
      }
    ]

    switch (expertiseLevel) {
      case 'basic':
        return basicTasks
      case 'advanced':
        return advancedTasks
      case 'technician':
        return technicianTasks
      default:
        return basicTasks
    }
  }

  useEffect(() => {
    setMaintenanceTasks(getMaintenanceTasksForLevel())
  }, [expertiseLevel])

  const markTaskCompleted = (taskId: string) => {
    setMaintenanceTasks(prev => prev.map(task => 
      task.id === taskId 
        ? { ...task, completed: true, lastCompleted: new Date() }
        : task
    ))
  }

  const openTaskDialog = (task: MaintenanceTask) => {
    setSelectedTask(task)
    setTaskDialogOpen(true)
  }

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'critical': return 'error'
      case 'high': return 'warning'
      case 'medium': return 'info'
      case 'low': return 'success'
      default: return 'default'
    }
  }

  const troubleshootingGuide = [
    {
      symptom: 'Mower won\'t start',
      causes: ['Battery depleted', 'Emergency stop activated', 'Service failure'],
      solutions: [
        'Check battery level in web interface',
        'Reset emergency stop button',
        'Restart system services',
        'Check power connections'
      ]
    },
    {
      symptom: 'Poor mowing pattern',
      causes: ['GPS signal weak', 'Sensor calibration needed', 'Boundary issues'],
      solutions: [
        'Move to open area for better GPS',
        'Recalibrate navigation sensors',
        'Check yard boundary settings',
        'Clean camera lens'
      ]
    },
    {
      symptom: 'Web interface not accessible',
      causes: ['Network connectivity', 'Service not running', 'Firewall blocking'],
      solutions: [
        'Check WiFi connection',
        'Restart web API service',
        'Verify firewall settings',
        'Check service logs'
      ]
    }
  ]

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Maintenance Guide - {expertiseLevel.charAt(0).toUpperCase() + expertiseLevel.slice(1)} Level
      </Typography>

      <Tabs value={activeTab} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
        <Tab icon={<ScheduleIcon />} label="Maintenance Schedule" />
        <Tab icon={<TestIcon />} label="Diagnostics" />
        <Tab icon={<WarningIcon />} label="Troubleshooting" />
        <Tab icon={<CalendarIcon />} label="Reminders" />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Typography variant="h6" gutterBottom>Scheduled Maintenance Tasks</Typography>
        
        <Alert severity="info" sx={{ mb: 3 }}>
          Regular maintenance ensures optimal performance and extends system lifespan. 
          Tasks are customized for your {expertiseLevel} expertise level.
        </Alert>

        <Grid container spacing={3}>
          {maintenanceTasks.map((task) => (
            <Grid item xs={12} md={6} lg={4} key={task.id}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                    <Typography variant="h6" component="h3">
                      {task.title}
                    </Typography>
                    <Chip 
                      label={task.priority}
                      color={getPriorityColor(task.priority) as any}
                      size="small"
                    />
                  </Box>
                  
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    {task.description}
                  </Typography>
                  
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                    <Typography variant="body2">
                      <strong>Frequency:</strong> {task.frequency}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Time:</strong> {task.estimatedTime}
                    </Typography>
                  </Box>

                  {task.completed && (
                    <Alert severity="success" sx={{ mb: 2 }}>
                      <CheckIcon sx={{ mr: 1 }} />
                      Completed {task.lastCompleted?.toLocaleDateString()}
                    </Alert>
                  )}

                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => openTaskDialog(task)}
                    >
                      View Details
                    </Button>
                    {!task.completed && (
                      <Button
                        variant="contained"
                        size="small"
                        onClick={() => markTaskCompleted(task.id)}
                      >
                        Mark Complete
                      </Button>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Typography variant="h6" gutterBottom>System Diagnostics</Typography>
        
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Run System Diagnostic</Typography>
              <Button
                variant="contained"
                startIcon={<TestIcon />}
                onClick={runDiagnostic}
                disabled={diagnosticRunning}
              >
                {diagnosticRunning ? 'Running...' : 'Start Diagnostic'}
              </Button>
            </Box>

            {diagnosticRunning && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>Running comprehensive system check...</Typography>
                <LinearProgress />
              </Box>
            )}

            {diagnosticResults && (
              <Box>
                <Alert 
                  severity={diagnosticResults.overall === 'good' ? 'success' : 'warning'} 
                  sx={{ mb: 2 }}
                >
                  Overall System Status: {diagnosticResults.overall.toUpperCase()}
                </Alert>

                <TableContainer component={Paper}>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Test</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Details</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {diagnosticResults.tests.map((test: any, index: number) => (
                        <TableRow key={index}>
                          <TableCell>{test.name}</TableCell>
                          <TableCell>
                            <Chip
                              label={test.status}
                              color={test.status === 'pass' ? 'success' : 'warning'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>{test.details}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            )}
          </CardContent>
        </Card>

        {expertiseLevel === 'technician' && (
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Advanced Diagnostics
                  </Typography>
                  <List>
                    <ListItem button>
                      <ListItemIcon><TestIcon /></ListItemIcon>
                      <ListItemText primary="Memory Test" secondary="Extended RAM validation" />
                    </ListItem>
                    <ListItem button>
                      <ListItemIcon><TestIcon /></ListItemIcon>
                      <ListItemText primary="Storage Test" secondary="Disk health and performance" />
                    </ListItem>
                    <ListItem button>
                      <ListItemIcon><TestIcon /></ListItemIcon>
                      <ListItemText primary="Network Test" secondary="Connectivity and latency" />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    System Logs
                  </Typography>
                  <List>
                    <ListItem button>
                      <ListItemIcon><DownloadIcon /></ListItemIcon>
                      <ListItemText primary="Download System Logs" />
                    </ListItem>
                    <ListItem button>
                      <ListItemIcon><RefreshIcon /></ListItemIcon>
                      <ListItemText primary="Clear Old Logs" />
                    </ListItem>
                    <ListItem button>
                      <ListItemIcon><WarningIcon /></ListItemIcon>
                      <ListItemText primary="View Error Logs" />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Typography variant="h6" gutterBottom>Troubleshooting Guide</Typography>
        
        {troubleshootingGuide.map((issue, index) => (
          <Accordion key={index}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="h6">{issue.symptom}</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" gutterBottom>Possible Causes:</Typography>
                  <List dense>
                    {issue.causes.map((cause, causeIndex) => (
                      <ListItem key={causeIndex}>
                        <ListItemIcon><InfoIcon color="warning" /></ListItemIcon>
                        <ListItemText primary={cause} />
                      </ListItem>
                    ))}
                  </List>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" gutterBottom>Solutions:</Typography>
                  <List dense>
                    {issue.solutions.map((solution, solutionIndex) => (
                      <ListItem key={solutionIndex}>
                        <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
                        <ListItemText primary={solution} />
                      </ListItem>
                    ))}
                  </List>
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>
        ))}
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Typography variant="h6" gutterBottom>Maintenance Reminders</Typography>
        
        <Alert severity="info" sx={{ mb: 3 }}>
          Set up automatic reminders for maintenance tasks to ensure nothing is missed.
        </Alert>

        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <NotificationIcon sx={{ mr: 1 }} />
                  Upcoming Tasks
                </Typography>
                <List>
                  <ListItem>
                    <ListItemIcon><WarningIcon color="warning" /></ListItemIcon>
                    <ListItemText 
                      primary="Weekly Cleaning"
                      secondary="Due in 2 days"
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><InfoIcon color="info" /></ListItemIcon>
                    <ListItemText 
                      primary="Monthly Battery Check"
                      secondary="Due in 5 days"
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
                  Notification Settings
                </Typography>
                <FormControlLabel
                  control={<Checkbox defaultChecked />}
                  label="Email notifications"
                />
                <FormControlLabel
                  control={<Checkbox defaultChecked />}
                  label="Web UI notifications"
                />
                <FormControlLabel
                  control={<Checkbox />}
                  label="SMS notifications"
                />
                <TextField
                  fullWidth
                  label="Email Address"
                  defaultValue="user@example.com"
                  sx={{ mt: 2 }}
                />
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Task Detail Dialog */}
      <Dialog
        open={taskDialogOpen}
        onClose={() => setTaskDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">{selectedTask?.title}</Typography>
            <IconButton onClick={() => setTaskDialogOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          {selectedTask && (
            <Box>
              <Typography variant="body1" gutterBottom>
                {selectedTask.description}
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <Chip label={`Priority: ${selectedTask.priority}`} color={getPriorityColor(selectedTask.priority) as any} />
                <Chip label={`Time: ${selectedTask.estimatedTime}`} />
                <Chip label={`Frequency: ${selectedTask.frequency}`} />
              </Box>

              <Typography variant="h6" gutterBottom>Steps:</Typography>
              <List>
                {selectedTask.steps.map((step, index) => (
                  <ListItem key={index}>
                    <ListItemIcon>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                        {index + 1}.
                      </Typography>
                    </ListItemIcon>
                    <ListItemText primary={step} />
                  </ListItem>
                ))}
              </List>

              {selectedTask.tools && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="h6" gutterBottom>Required Tools:</Typography>
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                    {selectedTask.tools.map((tool, index) => (
                      <Chip key={index} label={tool} variant="outlined" />
                    ))}
                  </Box>
                </Box>
              )}

              {selectedTask.safetyNotes && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  <Typography variant="subtitle2">Safety Notes:</Typography>
                  <List dense>
                    {selectedTask.safetyNotes.map((note, index) => (
                      <ListItem key={index}>
                        <ListItemText primary={note} />
                      </ListItem>
                    ))}
                  </List>
                </Alert>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTaskDialogOpen(false)}>Close</Button>
          <Button 
            variant="contained" 
            onClick={() => {
              if (selectedTask) {
                markTaskCompleted(selectedTask.id)
                setTaskDialogOpen(false)
              }
            }}
          >
            Mark as Complete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default MaintenanceGuide

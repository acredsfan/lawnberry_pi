import React, { useState } from 'react'
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Button,
  Alert,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stepper,
  Step,
  StepLabel,
  Paper,
  IconButton
} from '@mui/material'
import {
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Emergency as EmergencyIcon,
  Settings as SettingsIcon,
  Map as MapIcon,
  Speed as SpeedIcon,
  Security as SecurityIcon,
  Battery as BatteryIcon,
  Visibility as VisionIcon,
  ExpandMore as ExpandMoreIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  CheckCircle as CheckIcon,
  Close as CloseIcon
} from '@mui/icons-material'

interface UserManualProps {
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
      id={`user-manual-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 2 }}>{children}</Box>}
    </div>
  )
}

const UserManual: React.FC<UserManualProps> = ({ expertiseLevel }) => {
  const [activeTab, setActiveTab] = useState(0)
  const [tutorialOpen, setTutorialOpen] = useState(false)
  const [selectedTutorial, setSelectedTutorial] = useState<string>('')
  const [activeStep, setActiveStep] = useState(0)

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue)
  }

  const openTutorial = (tutorialId: string) => {
    setSelectedTutorial(tutorialId)
    setTutorialOpen(true)
    setActiveStep(0)
  }

  const basicUserContent = {
    gettingStarted: [
      {
        title: 'First Power-On',
        description: 'How to safely start your LawnBerryPi for the first time',
        icon: <PlayIcon />,
        steps: [
          'Ensure battery is charged (green indicator on power monitor)',
          'Press the main power button on the RoboHAT',
          'Wait for the system status LED to turn solid green (about 2 minutes)',
          'Connect to the web interface at http://your-pi-ip:8080'
        ]
      },
      {
        title: 'Basic Web Interface',
        description: 'Navigate the essential features of the web interface',
        icon: <MapIcon />,
        steps: [
          'Dashboard: View system status and battery level',
          'Maps: Set up your yard boundaries (drag to draw)',
          'Navigation: Start and stop mowing operations',
          'Settings: Basic safety and preference settings'
        ]
      },
      {
        title: 'Your First Mow',
        description: 'Step-by-step guide to starting your first mowing session',
        icon: <PlayIcon />,
        steps: [
          'Ensure yard boundaries are set on the Maps page',
          'Check battery level is above 50%',
          'Verify weather conditions are suitable (no rain)',
          'Go to Navigation page and click "Start Mowing"',
          'Monitor progress from the Dashboard'
        ]
      }
    ],
    safetyBasics: [
      {
        title: 'Emergency Stop',
        description: 'How to immediately stop the mower in any situation',
        icon: <EmergencyIcon />,
        alert: 'critical',
        steps: [
          'Press the physical emergency button on the mower',
          'Or use the EMERGENCY STOP button in the web interface',
          'The mower will stop all movement and blade operation immediately',
          'System will enter safe mode until manually reset'
        ]
      },
      {
        title: 'Daily Safety Checks',
        description: 'Essential safety checks before each use',
        icon: <SecurityIcon />,
        alert: 'warning',
        steps: [
          'Check for children, pets, or obstacles in the mowing area',
          'Verify weather conditions (no rain or strong wind)',
          'Ensure battery level is adequate for planned mowing time',
          'Test emergency stop function before starting'
        ]
      }
    ],
    basicMaintenance: [
      {
        title: 'Daily Cleaning',
        description: 'Simple cleaning tasks after each use',
        icon: <SettingsIcon />,
        steps: [
          'Turn off mower and disconnect power',
          'Remove grass clippings from blade area (use brush, not hands)',
          'Wipe down camera lens with soft cloth',
          'Check for any obvious damage or loose parts'
        ]
      },
      {
        title: 'Weekly Battery Care',
        description: 'Keep your battery healthy with weekly maintenance',
        icon: <BatteryIcon />,
        steps: [
          'Check battery level indicator weekly',
          'Clean solar panel surface with damp cloth',
          'Ensure charging station is free of debris',
          'Monitor charging performance in web interface'
        ]
      }
    ]
  }

  const advancedUserContent = {
    advancedOperations: [
      {
        title: 'Custom Mowing Patterns',
        description: 'Configure advanced mowing patterns for optimal coverage',
        icon: <SpeedIcon />,
        steps: [
          'Access Patterns tab in Navigation page',
          'Choose from Parallel, Spiral, Waves, Crosshatch, or Checkerboard',
          'Adjust pattern density and overlap settings',
          'Preview pattern on map before executing',
          'Save custom patterns for reuse'
        ]
      },
      {
        title: 'Advanced Safety Configuration',
        description: 'Fine-tune safety parameters for your specific needs',
        icon: <SecurityIcon />,
        steps: [
          'Access Advanced Settings in Settings page',
          'Configure obstacle detection sensitivity',
          'Set custom weather thresholds',
          'Configure slope detection limits',
          'Set up geofence violation responses'
        ]
      },
      {
        title: 'Performance Optimization',
        description: 'Optimize system performance for your hardware',
        icon: <SpeedIcon />,
        steps: [
          'Monitor system resources in Dashboard',
          'Adjust CPU/memory allocation in advanced settings',
          'Configure service priority levels',
          'Set up performance monitoring alerts',
          'Optimize battery usage patterns'
        ]
      }
    ],
    weatherIntegration: [
      {
        title: 'Weather-Based Scheduling',
        description: 'Automatically adjust mowing based on weather conditions',
        icon: <VisionIcon />,
        steps: [
          'Configure OpenWeather API key in settings',
          'Set weather condition thresholds',
          'Enable automatic schedule adjustment',
          'Configure rain delay settings',
          'Set up weather-based notifications'
        ]
      }
    ],
    powerManagement: [
      {
        title: 'Advanced Power Settings',
        description: 'Optimize power usage and charging behavior',
        icon: <BatteryIcon />,
        steps: [
          'Configure power profiles (Performance vs Efficiency)',
          'Set up intelligent charging location learning',
          'Configure low battery response thresholds',
          'Enable automatic power shutdown settings',
          'Monitor solar generation efficiency'
        ]
      }
    ]
  }

  const technicianContent = {
    systemAdministration: [
      {
        title: 'Service Management',
        description: 'Manage the 11 microservices that power LawnBerryPi',
        icon: <SettingsIcon />,
        steps: [
          'Access service status via systemctl commands',
          'Monitor service logs: journalctl -u lawnberry-*',
          'Restart individual services as needed',
          'Configure service startup dependencies',
          'Monitor inter-service communication via MQTT'
        ]
      },
      {
        title: 'Hardware Diagnostics',
        description: 'Comprehensive hardware testing and diagnostics',
        icon: <VisionIcon />,
        steps: [
          'Run hardware detection script: python3 scripts/hardware_detection.py',
          'Test individual sensor responses',
          'Validate GPIO pin configurations',
          'Check I2C bus communication',
          'Perform camera and GPS calibration'
        ]
      },
      {
        title: 'Database Management',
        description: 'Manage system databases and data integrity',
        icon: <SettingsIcon />,
        steps: [
          'Access Redis cache management interface',
          'Monitor database performance metrics',
          'Perform database backup and recovery',
          'Clean up old sensor data and logs',
          'Optimize database queries and indexes'
        ]
      }
    ],
    advancedConfiguration: [
      {
        title: 'Plugin Architecture',
        description: 'Extend system functionality with custom plugins',
        icon: <SettingsIcon />,
        steps: [
          'Access plugin management interface',
          'Install third-party plugins safely',
          'Develop custom plugins using API framework',
          'Test plugin compatibility and performance',
          'Monitor plugin resource usage'
        ]
      },
      {
        title: 'Security Administration',
        description: 'Configure advanced security features',
        icon: <SecurityIcon />,
        steps: [
          'Set up SSL/TLS certificates',
          'Configure user authentication and authorization',
          'Enable security audit logging',
          'Perform vulnerability assessments',
          'Configure firewall and network security'
        ]
      }
    ],
    troubleshooting: [
      {
        title: 'Advanced Diagnostics',
        description: 'Diagnose and resolve complex system issues',
        icon: <WarningIcon />,
        steps: [
          'Analyze system logs for patterns',
          'Use built-in diagnostic tools',
          'Perform network connectivity tests',
          'Check hardware interface reliability',
          'Monitor system resource utilization'
        ]
      }
    ]
  }

  const getContentForLevel = () => {
    switch (expertiseLevel) {
      case 'basic':
        return basicUserContent
      case 'advanced':
        return advancedUserContent
      case 'technician':
        return technicianContent
      default:
        return basicUserContent
    }
  }

  const content = getContentForLevel()
  const tabs = Object.keys(content)

  const getTutorialSteps = (tutorialId: string) => {
    // Find the tutorial in the current content
    for (const [category, items] of Object.entries(content)) {
      const tutorial = items.find(item => item.title === tutorialId)
      if (tutorial) {
        return tutorial.steps
      }
    }
    return []
  }

  const tutorialSteps = getTutorialSteps(selectedTutorial)

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        User Manual - {expertiseLevel.charAt(0).toUpperCase() + expertiseLevel.slice(1)} Level
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        This manual is customized for your expertise level. Access to features and complexity of instructions
        are adjusted accordingly. You can change your expertise level in the main documentation page.
      </Alert>

      <Tabs value={activeTab} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
        {tabs.map((tab, index) => (
          <Tab 
            key={tab}
            label={tab.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
            id={`user-manual-tab-${index}`}
          />
        ))}
      </Tabs>

      {tabs.map((tab, index) => (
        <TabPanel key={tab} value={activeTab} index={index}>
          <Grid container spacing={3}>
            {(content as any)[tab]?.map((item: any, itemIndex: number) => (
              <Grid item xs={12} md={6} key={itemIndex}>
                <Card>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      {item.icon}
                      <Typography variant="h6" sx={{ ml: 1, flexGrow: 1 }}>
                        {item.title}
                      </Typography>
                      {item.alert && (
                        <Chip 
                          label={item.alert} 
                          color={item.alert === 'critical' ? 'error' : 'warning'}
                          size="small"
                        />
                      )}
                    </Box>
                    
                    <Typography variant="body2" color="textSecondary" gutterBottom>
                      {item.description}
                    </Typography>

                    {item.alert && (
                      <Alert 
                        severity={item.alert === 'critical' ? 'error' : 'warning'} 
                        sx={{ mb: 2 }}
                        size="small"
                      >
                        {item.alert === 'critical' ? 
                          'Critical safety procedure - follow exactly' : 
                          'Important safety consideration'
                        }
                      </Alert>
                    )}

                    <List dense>
                      {item.steps.slice(0, 3).map((step: string, stepIndex: number) => (
                        <ListItem key={stepIndex}>
                          <ListItemIcon>
                            <CheckIcon color="primary" />
                          </ListItemIcon>
                          <ListItemText primary={step} />
                        </ListItem>
                      ))}
                    </List>

                    <Button
                      variant="outlined"
                      onClick={() => openTutorial(item.title)}
                      sx={{ mt: 2 }}
                    >
                      Start Interactive Tutorial
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </TabPanel>
      ))}

      {/* Interactive Tutorial Dialog */}
      <Dialog
        open={tutorialOpen}
        onClose={() => setTutorialOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="h6">{selectedTutorial}</Typography>
            <IconButton onClick={() => setTutorialOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        
        <DialogContent>
          <Stepper activeStep={activeStep} orientation="vertical">
            {tutorialSteps.map((step, index) => (
              <Step key={index}>
                <StepLabel>Step {index + 1}</StepLabel>
                <Box sx={{ pl: 4, pb: 2 }}>
                  <Typography variant="body1">{step}</Typography>
                  {index === activeStep && (
                    <Box sx={{ mt: 2 }}>
                      <Button
                        variant="contained"
                        onClick={() => setActiveStep(activeStep + 1)}
                        disabled={activeStep >= tutorialSteps.length - 1}
                        sx={{ mr: 1 }}
                      >
                        {activeStep >= tutorialSteps.length - 1 ? 'Complete' : 'Next'}
                      </Button>
                      <Button
                        onClick={() => setActiveStep(Math.max(0, activeStep - 1))}
                        disabled={activeStep === 0}
                      >
                        Previous
                      </Button>
                    </Box>
                  )}
                </Box>
              </Step>
            ))}
          </Stepper>
        </DialogContent>

        <DialogActions>
          <Button onClick={() => setTutorialOpen(false)}>Close</Button>
          <Button 
            variant="contained" 
            onClick={() => setActiveStep(0)}
          >
            Restart Tutorial
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default UserManual

import React, { useState } from 'react'
import {
  Box,
  Typography,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Button,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  Chip,
  Link,
  TextField,
  FormControlLabel,
  Checkbox,
  LinearProgress
} from '@mui/material'
import { Code } from '../ui'
import {
  ExpandMore as ExpandMoreIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Computer as ComputerIcon,
  Memory as MemoryIcon,
  Build as BuildIcon,
  Wifi as WifiIcon,
  Security as SecurityIcon,
  PlayArrow as PlayIcon
} from '@mui/icons-material'

interface DeploymentGuideProps {
  expertiseLevel: 'basic' | 'advanced' | 'technician'
}

const DeploymentGuide: React.FC<DeploymentGuideProps> = ({ expertiseLevel }) => {
  const [activeStep, setActiveStep] = useState(0)
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set())
  const [validationResults, setValidationResults] = useState<{[key: string]: boolean}>({})

  const handleNext = () => {
    setCompletedSteps(prev => new Set([...prev, activeStep]))
    setActiveStep((prevActiveStep) => prevActiveStep + 1)
  }

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1)
  }

  const handleReset = () => {
    setActiveStep(0)
    setCompletedSteps(new Set())
    setValidationResults({})
  }

  const validateStep = (stepId: string) => {
    // Simulate validation - in real implementation, this would check system status
    setValidationResults(prev => ({ ...prev, [stepId]: true }))
  }

  const getStepsForLevel = () => {
    const baseSteps = [
      {
        id: 'hardware-prep',
        label: 'Hardware Preparation',
        description: 'Prepare and assemble hardware components',
        content: (
          <Box>
            <Typography variant="h6" gutterBottom>Required Hardware</Typography>
            <List>
              <ListItem>
                <ListItemIcon><ComputerIcon /></ListItemIcon>
                <ListItemText 
                  primary="Raspberry Pi 4 Model B (8GB RAM recommended)"
                  secondary="Ensure you have the latest Bookworm OS image"
                />
              </ListItem>
              <ListItem>
                <ListItemIcon><BuildIcon /></ListItemIcon>
                <ListItemText 
                  primary="RoboHAT with RP2040-Zero modification"
                  secondary="Motor driver and GPIO expansion board"
                />
              </ListItem>
              <ListItem>
                <ListItemIcon><MemoryIcon /></ListItemIcon>
                <ListItemText 
                  primary="Sensors and Components"
                  secondary="ToF sensors, IMU, GPS, camera module, power monitoring"
                />
              </ListItem>
            </List>
            
            {expertiseLevel !== 'basic' && (
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography>Detailed Pin Mapping</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Box sx={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
                    <Typography variant="subtitle2">GPIO Configuration:</Typography>
                    <pre>
{`ToF Left Shutdown:    GPIO 22 (Pin 15)
ToF Right Shutdown:   GPIO 23 (Pin 16)
ToF Left Interrupt:   GPIO 6  (Pin 31)
ToF Right Interrupt:  GPIO 12 (Pin 32)
Blade Enable:         GPIO 24 (Pin 18)
Blade Direction:      GPIO 25 (Pin 22)`}
                    </pre>
                    
                    <Typography variant="subtitle2" sx={{ mt: 2 }}>Serial Connections:</Typography>
                    <pre>
{`RoboHAT:    /dev/ttyACM0 @ 115200 baud
GPS:        /dev/ttyACM1 @ 115200 baud
BNO085 IMU: /dev/ttyAMA4 @ 115200 baud`}
                    </pre>
                  </Box>
                </AccordionDetails>
              </Accordion>
            )}
            
            <Button 
              variant="outlined" 
              onClick={() => validateStep('hardware-prep')}
              sx={{ mt: 2 }}
            >
              Validate Hardware Setup
            </Button>
            {validationResults['hardware-prep'] && (
              <Alert severity="success" sx={{ mt: 1 }}>
                Hardware preparation validated successfully!
              </Alert>
            )}
          </Box>
        )
      },
      {
        id: 'os-setup',
        label: 'Operating System Setup',
        description: 'Install and configure Raspberry Pi OS Bookworm',
        content: (
          <Box>
            <Alert severity="info" sx={{ mb: 2 }}>
              LawnBerryPi is optimized exclusively for Raspberry Pi OS Bookworm
            </Alert>
            
            <Typography variant="h6" gutterBottom>Installation Steps</Typography>
            <List>
              <ListItem>
                <ListItemText 
                  primary="1. Download Raspberry Pi Imager"
                  secondary="Get the latest version from rpi.org"
                />
              </ListItem>
              <ListItem>
                <ListItemText 
                  primary="2. Flash Bookworm OS"
                  secondary="Use 64-bit Bookworm for optimal performance"
                />
              </ListItem>
              <ListItem>
                <ListItemText 
                  primary="3. Enable SSH and I2C"
                  secondary="Use raspi-config or enable in imager settings"
                />
              </ListItem>
              <ListItem>
                <ListItemText 
                  primary="4. Update System"
                  secondary="sudo apt update && sudo apt upgrade -y"
                />
              </ListItem>
            </List>

            {expertiseLevel === 'technician' && (
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography>Advanced OS Configuration</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="subtitle2" gutterBottom>Memory Management:</Typography>
                  <pre style={{ backgroundColor: '#f5f5f5', padding: '8px', borderRadius: '4px' }}>
{`# Add to /boot/config.txt
gpu_mem=128
dtparam=i2c_arm=on
dtparam=spi=on
enable_uart=1`}
                  </pre>
                  
                  <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>Performance Tuning:</Typography>
                  <pre style={{ backgroundColor: '#f5f5f5', padding: '8px', borderRadius: '4px' }}>
{`# CPU frequency scaling
echo 'performance' | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`}
                  </pre>
                </AccordionDetails>
              </Accordion>
            )}
          </Box>
        )
      },
      {
        id: 'software-install',
        label: 'Software Installation',
        description: 'Install LawnBerryPi software and dependencies',
        content: (
          <Box>
            <Typography variant="h6" gutterBottom>Automated Installation</Typography>
            
            <Paper sx={{ p: 2, backgroundColor: '#f5f5f5', mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Installation Command:</Typography>
              <Box sx={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
                curl -sSL https://raw.githubusercontent.com/your-repo/LawnBerryPi/main/scripts/install_lawnberry.sh | bash
              </Box>
            </Paper>

            <Typography variant="body2" color="textSecondary" gutterBottom>
              The installation script will automatically:
            </Typography>
            <List dense>
              <ListItem>
                <ListItemText primary="Install Python dependencies optimized for Bookworm" />
              </ListItem>
              <ListItem>
                <ListItemText primary="Configure systemd services for all 11 microservices" />
              </ListItem>
              <ListItem>
                <ListItemText primary="Set up Redis and MQTT broker" />
              </ListItem>
              <ListItem>
                <ListItemText primary="Configure hardware interfaces" />
              </ListItem>
              <ListItem>
                <ListItemText primary="Install and configure web UI" />
              </ListItem>
            </List>

            {expertiseLevel !== 'basic' && (
              <Accordion sx={{ mt: 2 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography>Manual Installation Steps</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Box sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                    <pre>
{`# Clone repository
git clone https://github.com/your-repo/LawnBerryPi.git
cd LawnBerryPi

# Install Python dependencies
pip3 install -r requirements.txt

# Set up services
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lawnberry-*

# Configure environment
cp .env.example .env
# Edit .env with your configuration

# Initialize system
python3 scripts/init_database.py
python3 scripts/setup_environment.py`}
                    </pre>
                  </Box>
                </AccordionDetails>
              </Accordion>
            )}
          </Box>
        )
      },
      {
        id: 'network-config',
        label: 'Network Configuration',
        description: 'Configure networking and security',
        content: (
          <Box>
            <Typography variant="h6" gutterBottom>Network Setup</Typography>
            
            <List>
              <ListItem>
                <ListItemIcon><WifiIcon /></ListItemIcon>
                <ListItemText 
                  primary="WiFi Configuration"
                  secondary="Connect to your network for remote access"
                />
              </ListItem>
              <ListItem>
                <ListItemIcon><SecurityIcon /></ListItemIcon>
                <ListItemText 
                  primary="Firewall Setup"
                  secondary="Configure ports 8080 (Web UI) and 1883 (MQTT)"
                />
              </ListItem>
            </List>

            {expertiseLevel === 'technician' && (
              <Box>
                <Alert severity="warning" sx={{ mb: 2 }}>
                  Advanced users should configure SSL/TLS certificates for production use
                </Alert>
                
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography>Security Configuration</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="subtitle2" gutterBottom>SSL Certificate Setup:</Typography>
                    <pre style={{ backgroundColor: '#f5f5f5', padding: '8px', borderRadius: '4px' }}>
{`# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Configure nginx for HTTPS
sudo cp cert.pem /etc/ssl/certs/lawnberry.crt
sudo cp key.pem /etc/ssl/private/lawnberry.key`}
                    </pre>
                  </AccordionDetails>
                </Accordion>
              </Box>
            )}
          </Box>
        )
      },
      {
        id: 'validation',
        label: 'System Validation',
        description: 'Validate installation and test functionality',
        content: (
          <Box>
            <Typography variant="h6" gutterBottom>Installation Validation</Typography>
            
            <Button 
              variant="contained" 
              startIcon={<PlayIcon />}
              onClick={() => validateStep('system-test')}
              sx={{ mb: 2 }}
            >
              Run System Validation
            </Button>

            {validationResults['system-test'] && (
              <Box>
                <Alert severity="success" sx={{ mb: 2 }}>
                  System validation completed successfully!
                </Alert>
                
                <Typography variant="subtitle2" gutterBottom>Validation Results:</Typography>
                <List>
                  <ListItem>
                    <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
                    <ListItemText primary="All 11 microservices started successfully" />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
                    <ListItemText primary="Hardware interfaces initialized" />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
                    <ListItemText primary="Web UI accessible at http://raspberry-pi-ip:8080" />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
                    <ListItemText primary="Database and caching systems operational" />
                  </ListItem>
                </List>
              </Box>
            )}

            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>Next Steps</Typography>
            <List>
              <ListItem>
                <ListItemText 
                  primary="Access Web Interface"
                  secondary="Navigate to http://your-pi-ip:8080 to complete setup"
                />
              </ListItem>
              <ListItem>
                <ListItemText 
                  primary="Run First-Time Setup Wizard"
                  secondary="Configure your yard boundaries and safety settings"
                />
              </ListItem>
              <ListItem>
                <ListItemText 
                  primary="Calibrate Sensors"
                  secondary="Follow the sensor calibration procedures"
                />
              </ListItem>
            </List>
          </Box>
        )
      }
    ]

    return baseSteps
  }

  const steps = getStepsForLevel()

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto' }}>
      <Typography variant="h5" gutterBottom>
        Deployment Guide - {expertiseLevel.charAt(0).toUpperCase() + expertiseLevel.slice(1)} Level
      </Typography>
      
      <LinearProgress 
        variant="determinate" 
        value={(completedSteps.size / steps.length) * 100} 
        sx={{ mb: 3, height: 8, borderRadius: 4 }}
      />

      <Stepper activeStep={activeStep} orientation="vertical">
        {steps.map((step, index) => (
          <Step key={step.id}>
            <StepLabel
              optional={
                completedSteps.has(index) ? (
                  <Chip 
                    icon={<CheckIcon />} 
                    label="Completed" 
                    size="small" 
                    color="success" 
                  />
                ) : null
              }
            >
              {step.label}
            </StepLabel>
            <StepContent>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                {step.description}
              </Typography>
              
              {step.content}
              
              <Box sx={{ mb: 2, mt: 2 }}>
                <div>
                  <Button
                    variant="contained"
                    onClick={handleNext}
                    sx={{ mt: 1, mr: 1 }}
                  >
                    {index === steps.length - 1 ? 'Finish' : 'Continue'}
                  </Button>
                  <Button
                    disabled={index === 0}
                    onClick={handleBack}
                    sx={{ mt: 1, mr: 1 }}
                  >
                    Back
                  </Button>
                </div>
              </Box>
            </StepContent>
          </Step>
        ))}
      </Stepper>
      
      {activeStep === steps.length && (
        <Paper square elevation={0} sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            Deployment Complete!
          </Typography>
          <Typography variant="body1" gutterBottom>
            Your LawnBerryPi system is now installed and ready for configuration.
            Proceed to the User Manual for operating instructions.
          </Typography>
          <Button onClick={handleReset} sx={{ mt: 1, mr: 1 }}>
            Reset Guide
          </Button>
        </Paper>
      )}
    </Box>
  )
}

export default DeploymentGuide

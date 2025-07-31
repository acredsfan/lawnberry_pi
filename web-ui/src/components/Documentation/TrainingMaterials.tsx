import React, { useState } from 'react'
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
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Paper,
  Alert,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  LinearProgress,
  Tabs,
  Tab,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  TextField,
  FormControlLabel,
  Checkbox,
  Radio,
  RadioGroup,
  FormControl,
  FormLabel
} from '@mui/material'
import {
  School as SchoolIcon,
  PlayArrow as PlayIcon,
  Quiz as QuizIcon,
  MenuBook as BookIcon,
  Speed as SpeedIcon,
  Security as SecurityIcon,
  Build as BuildIcon,
  Map as MapIcon,
  Close as CloseIcon,
  ExpandMore as ExpandMoreIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Lightbulb as TipIcon,
  Warning as WarningIcon,
  Star as StarIcon,
  AccessTime as TimeIcon
} from '@mui/icons-material'

interface TrainingMaterialsProps {
  expertiseLevel: 'basic' | 'advanced' | 'technician'
}

interface TrainingModule {
  id: string
  title: string
  description: string
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  estimatedTime: string
  prerequisites?: string[]
  objectives: string[]
  content: TrainingStep[]
  quiz?: QuizQuestion[]
  completed?: boolean
  score?: number
}

interface TrainingStep {
  id: string
  title: string
  type: 'instruction' | 'interactive' | 'video' | 'quiz' | 'practice'
  content: string
  tips?: string[]
  warnings?: string[]
  interactive?: {
    type: 'button_click' | 'form_fill' | 'simulation'
    target?: string
    validation?: any
  }
}

interface QuizQuestion {
  id: string
  question: string
  type: 'multiple_choice' | 'true_false' | 'short_answer'
  options?: string[]
  correct_answer: string | number
  explanation: string
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
      id={`training-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 2 }}>{children}</Box>}
    </div>
  )
}

const TrainingMaterials: React.FC<TrainingMaterialsProps> = ({ expertiseLevel }) => {
  const [activeTab, setActiveTab] = useState(0)
  const [selectedModule, setSelectedModule] = useState<TrainingModule | null>(null)
  const [moduleDialogOpen, setModuleDialogOpen] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [quizAnswers, setQuizAnswers] = useState<{[key: string]: any}>({})
  const [quizResults, setQuizResults] = useState<{[key: string]: boolean}>({})
  const [moduleProgress, setModuleProgress] = useState<{[key: string]: number}>({})

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue)
  }

  const startModule = (module: TrainingModule) => {
    setSelectedModule(module)
    setCurrentStep(0)
    setQuizAnswers({})
    setQuizResults({})
    setModuleDialogOpen(true)
  }

  const completeStep = () => {
    if (selectedModule && currentStep < selectedModule.content.length - 1) {
      setCurrentStep(currentStep + 1)
      const progress = ((currentStep + 2) / selectedModule.content.length) * 100
      setModuleProgress(prev => ({ ...prev, [selectedModule.id]: progress }))
    } else {
      // Module completed
      if (selectedModule) {
        setModuleProgress(prev => ({ ...prev, [selectedModule.id]: 100 }))
      }
    }
  }

  const submitQuiz = () => {
    if (!selectedModule?.quiz) return
    
    const results: {[key: string]: boolean} = {}
    let correctCount = 0
    
    selectedModule.quiz.forEach(question => {
      const userAnswer = quizAnswers[question.id]
      const isCorrect = userAnswer === question.correct_answer
      results[question.id] = isCorrect
      if (isCorrect) correctCount++
    })
    
    setQuizResults(results)
    const score = (correctCount / selectedModule.quiz.length) * 100
    
    // Update module completion
    setModuleProgress(prev => ({ ...prev, [selectedModule.id]: 100 }))
  }

  const getTrainingModulesForLevel = (): TrainingModule[] => {
    const basicModules: TrainingModule[] = [
      {
        id: 'getting-started',
        title: 'Getting Started with LawnBerryPi',
        description: 'Learn the basics of operating your autonomous mower',
        difficulty: 'beginner',
        estimatedTime: '30 minutes',
        objectives: [
          'Understand basic safety procedures',
          'Learn to start and stop mowing operations',
          'Navigate the web interface',
          'Perform basic troubleshooting'
        ],
        content: [
          {
            id: 'welcome',
            title: 'Welcome to LawnBerryPi',
            type: 'instruction',
            content: 'Welcome to your LawnBerryPi autonomous mowing system! This tutorial will guide you through the essential operations you need to know for safe and effective use.',
            tips: ['Take your time to understand each concept', 'Don\'t skip the safety sections']
          },
          {
            id: 'safety-basics',
            title: 'Safety First',
            type: 'instruction',
            content: 'Safety is our top priority. Always remember: Never approach the mower while it\'s operating, always use the emergency stop when needed, keep children and pets away from the mowing area.',
            warnings: ['Emergency stop button locations', 'Never touch the blade area', 'Always turn off before maintenance']
          },
          {
            id: 'web-interface',
            title: 'Web Interface Overview',
            type: 'interactive',
            content: 'Let\'s explore the web interface. The dashboard shows your mower\'s current status, battery level, and location.',
            interactive: {
              type: 'simulation',
              target: 'dashboard'
            }
          },
          {
            id: 'first-mow',
            title: 'Your First Mowing Session',
            type: 'practice',
            content: 'Now let\'s start your first mowing session. Go to the Navigation page and click the Start button.',
            tips: ['Check battery level first', 'Verify boundaries are set', 'Monitor the first few minutes']
          }
        ],
        quiz: [
          {
            id: 'q1',
            question: 'What should you do before starting a mowing session?',
            type: 'multiple_choice',
            options: [
              'Check battery level',
              'Verify boundaries are set',
              'Check weather conditions',
              'All of the above'
            ],
            correct_answer: 3,
            explanation: 'Always perform all safety checks before starting'
          },
          {
            id: 'q2',
            question: 'Can you approach the mower while it\'s operating?',
            type: 'true_false',
            options: ['True', 'False'],
            correct_answer: 1,
            explanation: 'Never approach the mower while it\'s operating for safety reasons'
          }
        ]
      },
      {
        id: 'boundary-setup',
        title: 'Setting Up Yard Boundaries',
        description: 'Learn to define your mowing area using the interactive map',
        difficulty: 'beginner',
        estimatedTime: '20 minutes',
        objectives: [
          'Use the interactive map tools',
          'Draw accurate yard boundaries',
          'Set up no-go zones',
          'Test boundary accuracy'
        ],
        content: [
          {
            id: 'map-tools',
            title: 'Map Drawing Tools',
            type: 'instruction',
            content: 'The Maps page provides tools to draw your yard boundaries and no-go zones. Use the polygon tool for boundaries and circle tool for no-go zones.',
            tips: ['Use satellite view for better accuracy', 'Start with outer boundary first']
          },
          {
            id: 'draw-boundary',
            title: 'Drawing Your Boundary',
            type: 'interactive',
            content: 'Click points around your yard perimeter to create the boundary. The system will connect the points to form a polygon.',
            interactive: {
              type: 'simulation',
              target: 'maps'
            }
          }
        ]
      }
    ]

    const advancedModules: TrainingModule[] = [
      ...basicModules,
      {
        id: 'advanced-patterns',
        title: 'Advanced Mowing Patterns',
        description: 'Master custom mowing patterns for optimal coverage',
        difficulty: 'intermediate',
        estimatedTime: '45 minutes',
        prerequisites: ['getting-started'],
        objectives: [
          'Understand different mowing patterns',
          'Choose optimal patterns for your yard',
          'Configure pattern parameters',
          'Monitor mowing efficiency'
        ],
        content: [
          {
            id: 'pattern-types',
            title: 'Types of Mowing Patterns',
            type: 'instruction',
            content: 'LawnBerryPi supports 5 mowing patterns: Parallel (straight lines), Spiral (inside-out or outside-in), Waves (sinusoidal curves), Crosshatch (perpendicular lines), and Checkerboard (alternating squares).',
            tips: ['Parallel is most efficient for rectangular yards', 'Spiral works well for circular areas', 'Waves prevent grass wear patterns']
          },
          {
            id: 'pattern-selection',
            title: 'Choosing the Right Pattern',
            type: 'instruction',
            content: 'Pattern selection depends on your yard shape, grass type, and efficiency goals. Rectangular yards benefit from parallel patterns, while irregular shapes work better with spiral patterns.',
            tips: ['Consider your yard\'s dominant shape', 'Factor in obstacle density', 'Think about grass health']
          }
        ]
      },
      {
        id: 'weather-integration',
        title: 'Weather-Based Operation',
        description: 'Configure automatic weather-based scheduling',
        difficulty: 'intermediate',
        estimatedTime: '30 minutes',
        objectives: [
          'Set up weather API integration',
          'Configure weather thresholds',
          'Enable automatic scheduling',
          'Monitor weather-based decisions'
        ],
        content: [
          {
            id: 'weather-setup',
            title: 'Weather API Configuration',
            type: 'instruction',
            content: 'Connect your system to OpenWeather API for real-time weather data and forecasting capabilities.',
            tips: ['Get free API key from openweathermap.org', 'Set appropriate location coordinates']
          }
        ]
      }
    ]

    const technicianModules: TrainingModule[] = [
      ...advancedModules,
      {
        id: 'system-administration',
        title: 'System Administration',
        description: 'Advanced system management and troubleshooting',
        difficulty: 'advanced',
        estimatedTime: '90 minutes',
        prerequisites: ['getting-started', 'advanced-patterns'],
        objectives: [
          'Manage system services',
          'Monitor system performance',
          'Troubleshoot complex issues',
          'Perform system maintenance'
        ],
        content: [
          {
            id: 'service-management',
            title: 'Managing System Services',
            type: 'instruction',
            content: 'LawnBerryPi runs 11 microservices. Learn to monitor, restart, and troubleshoot each service using systemctl commands.',
            tips: ['Use journalctl for service logs', 'Monitor service dependencies', 'Understand service startup order']
          },
          {
            id: 'performance-monitoring',
            title: 'Performance Monitoring',
            type: 'instruction',
            content: 'Monitor CPU, memory, and I/O usage to ensure optimal system performance. Use built-in monitoring tools and external utilities.',
            tips: ['Set up automated alerts', 'Monitor resource usage trends', 'Identify performance bottlenecks']
          }
        ]
      },
      {
        id: 'plugin-development',
        title: 'Plugin Development',
        description: 'Create custom plugins to extend system functionality',
        difficulty: 'advanced',
        estimatedTime: '120 minutes',
        prerequisites: ['system-administration'],
        objectives: [
          'Understand plugin architecture',
          'Create basic plugins',
          'Test plugin functionality',
          'Deploy plugins safely'
        ],
        content: [
          {
            id: 'plugin-architecture',
            title: 'Understanding Plugin Architecture',
            type: 'instruction',
            content: 'Plugins extend LawnBerryPi functionality through event hooks and API calls. Learn the plugin lifecycle and security model.',
            tips: ['Follow security best practices', 'Test thoroughly before deployment', 'Document plugin functionality']
          }
        ]
      }
    ]

    switch (expertiseLevel) {
      case 'basic':
        return basicModules
      case 'advanced':
        return advancedModules
      case 'technician':
        return technicianModules
      default:
        return basicModules
    }
  }

  const modules = getTrainingModulesForLevel()

  const quickReference = [
    {
      category: 'Emergency Procedures',
      items: [
        { title: 'Emergency Stop', shortcut: 'Physical button or web UI', description: 'Immediately stop all operations' },
        { title: 'Manual Override', shortcut: 'Navigation > Manual Control', description: 'Take direct control of movement' },
        { title: 'System Shutdown', shortcut: 'Settings > Power > Shutdown', description: 'Safely shut down system' }
      ]
    },
    {
      category: 'Common Commands',
      items: [
        { title: 'Start Mowing', shortcut: 'Navigation > Start', description: 'Begin mowing operation' },
        { title: 'Return to Base', shortcut: 'Navigation > Return Home', description: 'Navigate to charging station' },
        { title: 'Check Status', shortcut: 'Dashboard', description: 'View system status and battery' }
      ]
    },
    {
      category: 'Troubleshooting',
      items: [
        { title: 'Connection Issues', shortcut: 'Check WiFi settings', description: 'Verify network connectivity' },
        { title: 'GPS Problems', shortcut: 'Move to open area', description: 'Improve satellite reception' },
        { title: 'Battery Issues', shortcut: 'Check charging station', description: 'Verify power connections' }
      ]
    }
  ]

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case 'beginner': return 'success'
      case 'intermediate': return 'warning'
      case 'advanced': return 'error'
      default: return 'default'
    }
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Training Materials - {expertiseLevel.charAt(0).toUpperCase() + expertiseLevel.slice(1)} Level
      </Typography>

      <Tabs value={activeTab} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
        <Tab icon={<SchoolIcon />} label="Interactive Tutorials" />
        <Tab icon={<BookIcon />} label="Quick Reference" />
        <Tab icon={<QuizIcon />} label="Knowledge Checks" />
        <Tab icon={<StarIcon />} label="Certification" />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Typography variant="h6" gutterBottom>Interactive Training Modules</Typography>
        
        <Alert severity="info" sx={{ mb: 3 }}>
          Complete these interactive modules to build your expertise with LawnBerryPi. 
          Modules are tailored to your {expertiseLevel} level.
        </Alert>

        <Grid container spacing={3}>
          {modules.map((module) => (
            <Grid item xs={12} md={6} lg={4} key={module.id}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                    <Typography variant="h6" component="h3">
                      {module.title}
                    </Typography>
                    <Chip 
                      label={module.difficulty}
                      color={getDifficultyColor(module.difficulty) as any}
                      size="small"
                    />
                  </Box>
                  
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    {module.description}
                  </Typography>
                  
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <TimeIcon sx={{ mr: 1, fontSize: 'small' }} />
                    <Typography variant="body2">{module.estimatedTime}</Typography>
                  </Box>

                  {moduleProgress[module.id] && (
                    <Box sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="body2">Progress</Typography>
                        <Typography variant="body2">{Math.round(moduleProgress[module.id])}%</Typography>
                      </Box>
                      <LinearProgress 
                        variant="determinate" 
                        value={moduleProgress[module.id]} 
                        sx={{ height: 8, borderRadius: 4 }}
                      />
                    </Box>
                  )}

                  {module.prerequisites && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>Prerequisites:</Typography>
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                        {module.prerequisites.map((prereq, index) => (
                          <Chip key={index} label={prereq} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                  )}

                  <Button
                    variant="contained"
                    startIcon={<PlayIcon />}
                    onClick={() => startModule(module)}
                    disabled={moduleProgress[module.id] === 100}
                  >
                    {moduleProgress[module.id] === 100 ? 'Completed' : 'Start Module'}
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Typography variant="h6" gutterBottom>Quick Reference Guide</Typography>
        
        <Grid container spacing={3}>
          {quickReference.map((category, index) => (
            <Grid item xs={12} md={6} key={index}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {category.category}
                  </Typography>
                  <List>
                    {category.items.map((item, itemIndex) => (
                      <ListItem key={itemIndex}>
                        <ListItemIcon>
                          <TipIcon color="primary" />
                        </ListItemIcon>
                        <ListItemText
                          primary={item.title}
                          secondary={
                            <Box>
                              <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                                {item.shortcut}
                              </Typography>
                              <Typography variant="body2" color="textSecondary">
                                {item.description}
                              </Typography>
                            </Box>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Typography variant="h6" gutterBottom>Knowledge Assessment</Typography>
        
        <Alert severity="info" sx={{ mb: 3 }}>
          Test your understanding with these knowledge checks. Complete training modules first for best results.
        </Alert>

        <Grid container spacing={3}>
          {modules.filter(m => m.quiz).map((module) => (
            <Grid item xs={12} md={6} key={module.id}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {module.title} Quiz
                  </Typography>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    {module.quiz?.length} questions
                  </Typography>
                  <Button
                    variant="outlined"
                    startIcon={<QuizIcon />}
                    onClick={() => startModule(module)}
                  >
                    Take Quiz
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Typography variant="h6" gutterBottom>Certification Program</Typography>
        
        <Alert severity="info" sx={{ mb: 3 }}>
          Earn certificates by completing training modules and passing assessments.
        </Alert>

        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <StarIcon sx={{ mr: 1, color: '#4caf50' }} />
                  Basic Operator
                </Typography>
                <Typography variant="body2" gutterBottom>
                  Complete basic training modules and safety assessment
                </Typography>
                <LinearProgress variant="determinate" value={75} sx={{ mb: 2 }} />
                <Typography variant="body2">3 of 4 modules completed</Typography>
              </CardContent>
            </Card>
          </Grid>

          {expertiseLevel !== 'basic' && (
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    <StarIcon sx={{ mr: 1, color: '#ff9800' }} />
                    Advanced User
                  </Typography>
                  <Typography variant="body2" gutterBottom>
                    Master advanced features and customization
                  </Typography>
                  <LinearProgress variant="determinate" value={25} sx={{ mb: 2 }} />
                  <Typography variant="body2">1 of 4 modules completed</Typography>
                </CardContent>
              </Card>
            </Grid>
          )}

          {expertiseLevel === 'technician' && (
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    <StarIcon sx={{ mr: 1, color: '#f44336' }} />
                    System Administrator
                  </Typography>
                  <Typography variant="body2" gutterBottom>
                    Complete technical training and system management
                  </Typography>
                  <LinearProgress variant="determinate" value={0} sx={{ mb: 2 }} />
                  <Typography variant="body2">0 of 6 modules completed</Typography>
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      </TabPanel>

      {/* Training Module Dialog */}
      <Dialog
        open={moduleDialogOpen}
        onClose={() => setModuleDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">{selectedModule?.title}</Typography>
            <IconButton onClick={() => setModuleDialogOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          {selectedModule && (
            <Box>
              {/* Progress indicator */}
              <LinearProgress 
                variant="determinate" 
                value={((currentStep + 1) / selectedModule.content.length) * 100}
                sx={{ mb: 3, height: 8, borderRadius: 4 }}
              />

              {/* Current step content */}
              {selectedModule.content[currentStep] && (
                <Box>
                  <Typography variant="h6" gutterBottom>
                    {selectedModule.content[currentStep].title}
                  </Typography>
                  
                  <Typography variant="body1" paragraph>
                    {selectedModule.content[currentStep].content}
                  </Typography>

                  {selectedModule.content[currentStep].tips && (
                    <Alert severity="info" sx={{ mb: 2 }}>
                      <Typography variant="subtitle2">Tips:</Typography>
                      <List dense>
                        {selectedModule.content[currentStep].tips?.map((tip, index) => (
                          <ListItem key={index}>
                            <ListItemIcon><TipIcon /></ListItemIcon>
                            <ListItemText primary={tip} />
                          </ListItem>
                        ))}
                      </List>
                    </Alert>
                  )}

                  {selectedModule.content[currentStep].warnings && (
                    <Alert severity="warning" sx={{ mb: 2 }}>
                      <Typography variant="subtitle2">Important:</Typography>
                      <List dense>
                        {selectedModule.content[currentStep].warnings?.map((warning, index) => (
                          <ListItem key={index}>
                            <ListItemIcon><WarningIcon /></ListItemIcon>
                            <ListItemText primary={warning} />
                          </ListItem>
                        ))}
                      </List>
                    </Alert>
                  )}
                </Box>
              )}

              {/* Quiz section */}
              {currentStep === selectedModule.content.length && selectedModule.quiz && (
                <Box>
                  <Typography variant="h6" gutterBottom>Knowledge Check</Typography>
                  {selectedModule.quiz.map((question, index) => (
                    <Card key={question.id} sx={{ mb: 2 }}>
                      <CardContent>
                        <Typography variant="body1" gutterBottom>
                          {index + 1}. {question.question}
                        </Typography>
                        
                        {question.type === 'multiple_choice' && (
                          <FormControl component="fieldset">
                            <RadioGroup
                              value={quizAnswers[question.id] || ''}
                              onChange={(e) => setQuizAnswers(prev => ({
                                ...prev,
                                [question.id]: parseInt(e.target.value)
                              }))}
                            >
                              {question.options?.map((option, optionIndex) => (
                                <FormControlLabel
                                  key={optionIndex}
                                  value={optionIndex}
                                  control={<Radio />}
                                  label={option}
                                />
                              ))}
                            </RadioGroup>
                          </FormControl>
                        )}

                        {question.type === 'true_false' && (
                          <FormControl component="fieldset">
                            <RadioGroup
                              value={quizAnswers[question.id] || ''}
                              onChange={(e) => setQuizAnswers(prev => ({
                                ...prev,
                                [question.id]: parseInt(e.target.value)
                              }))}
                            >
                              <FormControlLabel value={0} control={<Radio />} label="True" />
                              <FormControlLabel value={1} control={<Radio />} label="False" />
                            </RadioGroup>
                          </FormControl>
                        )}

                        {quizResults[question.id] !== undefined && (
                          <Alert 
                            severity={quizResults[question.id] ? 'success' : 'error'} 
                            sx={{ mt: 2 }}
                          >
                            <Typography variant="body2">
                              {question.explanation}
                            </Typography>
                          </Alert>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                  
                  {Object.keys(quizResults).length === 0 && (
                    <Button
                      variant="contained"
                      onClick={submitQuiz}
                      disabled={Object.keys(quizAnswers).length !== selectedModule.quiz.length}
                    >
                      Submit Quiz
                    </Button>
                  )}
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setModuleDialogOpen(false)}>Close</Button>
          {selectedModule && currentStep < selectedModule.content.length && (
            <Button variant="contained" onClick={completeStep}>
              {currentStep === selectedModule.content.length - 1 ? 'Finish' : 'Next Step'}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default TrainingMaterials

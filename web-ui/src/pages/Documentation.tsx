import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  Tabs,
  Tab,
  Alert,
  TextField,
  InputAdornment
} from '@mui/material'
import {
  Description as DocumentationIcon,
  Build as BuildIcon,
  Person as PersonIcon,
  Engineering as EngineeringIcon,
  School as SchoolIcon,
  Search as SearchIcon,
  Settings as MaintenanceIcon
} from '@mui/icons-material'
import {
  DeploymentGuide,
  UserManual,
  TechnicalReference,
  MaintenanceGuide,
  TrainingMaterials
} from '../components/Documentation'

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
      id={`documentation-tabpanel-${index}`}
      aria-labelledby={`documentation-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  )
}

const Documentation: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0)
  const [expertiseLevel, setExpertiseLevel] = useState<'basic' | 'advanced' | 'technician'>('basic')
  const [searchTerm, setSearchTerm] = useState('')

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue)
  }

  const handleExpertiseLevelChange = (level: 'basic' | 'advanced' | 'technician') => {
    setExpertiseLevel(level)
  }

  const documentationTabs = [
    { id: 'deployment', title: 'Deployment Guide', icon: <BuildIcon /> },
    { id: 'user-manual', title: 'User Manual', icon: <PersonIcon /> },
    { id: 'technical-reference', title: 'Technical Reference', icon: <EngineeringIcon /> },
    { id: 'maintenance', title: 'Maintenance Guide', icon: <MaintenanceIcon /> },
    { id: 'training', title: 'Training Materials', icon: <SchoolIcon /> }
  ]

  const expertiseLevels = [
    {
      level: 'basic' as const,
      title: 'Basic User',
      description: 'Essential operations and safety',
      color: '#4caf50'
    },
    {
      level: 'advanced' as const,
      title: 'Advanced User',
      description: 'Full feature access and customization',
      color: '#ff9800'
    },
    {
      level: 'technician' as const,
      title: 'Technician',
      description: 'Complete system administration',
      color: '#f44336'
    }
  ]

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Paper sx={{ p: 3, mb: 2 }}>
        <Typography variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <DocumentationIcon color="primary" />
          LawnBerryPi Documentation
        </Typography>
        
        {/* Expertise Level Selector */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="h6" gutterBottom>Select Your Expertise Level:</Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {expertiseLevels.map((level) => (
              <Chip
                key={level.level}
                label={level.title}
                variant={expertiseLevel === level.level ? 'filled' : 'outlined'}
                color={expertiseLevel === level.level ? 'primary' : 'default'}
                onClick={() => handleExpertiseLevelChange(level.level)}
                sx={{ 
                  borderColor: level.color,
                  color: expertiseLevel === level.level ? 'white' : level.color,
                  backgroundColor: expertiseLevel === level.level ? level.color : 'transparent'
                }}
              />
            ))}
          </Box>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
            {expertiseLevels.find(l => l.level === expertiseLevel)?.description}
          </Typography>
        </Box>

        {/* Search */}
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Search documentation..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ maxWidth: 400 }}
        />
      </Paper>

      {/* Content */}
      <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          {documentationTabs.map((tab, index) => (
            <Tab
              key={tab.id}
              label={tab.title}
              icon={tab.icon}
              iconPosition="start"
              id={`documentation-tab-${index}`}
              aria-controls={`documentation-tabpanel-${index}`}
            />
          ))}
        </Tabs>

        <TabPanel value={activeTab} index={0}>
          <DeploymentGuide expertiseLevel={expertiseLevel} />
        </TabPanel>

        <TabPanel value={activeTab} index={1}>
          <UserManual expertiseLevel={expertiseLevel} />
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          <TechnicalReference expertiseLevel={expertiseLevel} />
        </TabPanel>

        <TabPanel value={activeTab} index={3}>
          <MaintenanceGuide expertiseLevel={expertiseLevel} />
        </TabPanel>

        <TabPanel value={activeTab} index={4}>
          <TrainingMaterials expertiseLevel={expertiseLevel} />
        </TabPanel>
      </Box>
    </Box>
  )
}

export default Documentation

import React from 'react'
import { Box, AppBar, Toolbar, Typography, IconButton, Drawer, List, ListItem, ListItemIcon, ListItemText, Badge, useTheme, useMediaQuery } from '@mui/material'
import { Menu as MenuIcon, Dashboard as DashboardIcon, Navigation as NavigationIcon, Map as MapIcon, Settings as SettingsIcon, PhotoCamera as TrainingIcon, Notifications as NotificationsIcon, Warning as EmergencyIcon } from '@mui/icons-material'
import { useSelector, useDispatch } from 'react-redux'
import { useNavigate, useLocation } from 'react-router-dom'
import { RootState } from '../../store/store'
import { toggleSidebar, setSidebarOpen, openModal } from '../../store/slices/uiSlice'
import { setEmergencyStop } from '../../store/slices/mowerSlice'
import ConnectionStatus from '../ConnectionStatus/ConnectionStatus'
import EmergencyButton from '../EmergencyButton/EmergencyButton'
import Logo from '../Logo'

interface LayoutProps {
  children: React.ReactNode
}

const drawerWidth = 240

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const location = useLocation()
  
  const { sidebarOpen, notifications, connectionStatus } = useSelector((state: RootState) => state.ui)
  const { emergencyStop } = useSelector((state: RootState) => state.mower)

  const unreadCount = notifications.filter(n => !n.read).length

  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: DashboardIcon, path: '/dashboard' },
    { id: 'navigation', label: 'Navigation', icon: NavigationIcon, path: '/navigation' },
    { id: 'maps', label: 'Maps', icon: MapIcon, path: '/maps' },
    { id: 'training', label: 'Training', icon: TrainingIcon, path: '/training' },
    { id: 'settings', label: 'Settings', icon: SettingsIcon, path: '/settings' },
  ]

  const handleDrawerToggle = () => {
    dispatch(toggleSidebar())
  }

  const handleMenuClick = (path: string) => {
    navigate(path)
    if (isMobile) {
      dispatch(setSidebarOpen(false))
    }
  }

  const handleEmergencyStop = () => {
    dispatch(setEmergencyStop(true))
    dispatch(openModal('emergencyStop'))
  }

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Toolbar>
        <Logo size={32} showText={true} />
      </Toolbar>
      
      <List sx={{ flexGrow: 1 }}>
        {menuItems.map((item) => {
          const Icon = item.icon
          const isActive = location.pathname === item.path
          
          return (
            <ListItem
              key={item.id}
              onClick={() => handleMenuClick(item.path)}
              sx={{
                cursor: 'pointer',
                backgroundColor: isActive ? theme.palette.primary.main + '20' : 'transparent',
                borderRight: isActive ? `3px solid ${theme.palette.primary.main}` : 'none',
                '&:hover': {
                  backgroundColor: theme.palette.primary.main + '10',
                }
              }}
            >
              <ListItemIcon>
                <Icon color={isActive ? 'primary' : 'inherit'} />
              </ListItemIcon>
              <ListItemText 
                primary={item.label}
                primaryTypographyProps={{
                  color: isActive ? 'primary' : 'inherit',
                  fontWeight: isActive ? 'medium' : 'normal'
                }}
              />
            </ListItem>
          )
        })}
      </List>

      <Box sx={{ p: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
        <ConnectionStatus />
      </Box>
    </Box>
  )

  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${sidebarOpen ? drawerWidth : 0}px)` },
          ml: { md: sidebarOpen ? `${drawerWidth}px` : 0 },
          zIndex: theme.zIndex.drawer + 1,
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { md: sidebarOpen ? 'none' : 'block' } }}
          >
            <MenuIcon />
          </IconButton>
          
          <Box sx={{ display: { xs: 'none', md: sidebarOpen ? 'none' : 'flex' }, mr: 2 }}>
            <Logo size={36} showText={true} />
          </Box>
          
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {menuItems.find(item => item.path === location.pathname)?.label || 'Dashboard'}
          </Typography>

          <IconButton color="inherit" onClick={() => dispatch(openModal('settings'))}>
            <Badge badgeContent={unreadCount} color="secondary">
              <NotificationsIcon />
            </Badge>
          </IconButton>

          <EmergencyButton 
            onClick={handleEmergencyStop}
            active={emergencyStop}
            sx={{ ml: 2 }}
          />
        </Toolbar>
      </AppBar>

      <Box
        component="nav"
        sx={{ width: { md: sidebarOpen ? drawerWidth : 0 }, flexShrink: { md: 0 } }}
      >
        <Drawer
          variant={isMobile ? 'temporary' : 'persistent'}
          open={sidebarOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better mobile performance
          }}
          sx={{
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
              borderRight: `1px solid ${theme.palette.divider}`,
            },
          }}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${sidebarOpen ? drawerWidth : 0}px)` },
          height: '100vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Toolbar /> {/* Spacer for fixed AppBar */}
        <Box sx={{ flexGrow: 1, overflow: 'auto', p: { xs: 1, sm: 2, md: 3 } }}>
          {children}
        </Box>
      </Box>
    </Box>
  )
}

export default Layout

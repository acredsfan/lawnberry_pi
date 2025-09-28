import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/control',
      name: 'Control',
      component: () => import('@/views/ControlView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/maps',
      name: 'Maps',
      component: () => import('@/views/MapsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/planning',
      name: 'Planning',
      component: () => import('@/views/PlanningView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/ai',
      name: 'AI',
      component: () => import('@/views/AIView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/telemetry',
      name: 'Telemetry',
      component: () => import('@/views/TelemetryView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/docs',
      name: 'DocsHub',
      component: () => import('@/views/DocsHubView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false }
    }
  ]
})

// Navigation guard for authentication
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  
  // Check if route requires authentication
  if (to.meta.requiresAuth) {
    // If not authenticated, check if we have a valid token
    if (!authStore.isAuthenticated && authStore.token) {
      try {
        // Validate the stored token
        await authStore.validateSession()
      } catch (error) {
        console.warn('Token validation failed:', error)
        // Token is invalid, clear it and redirect to login
        await authStore.logout()
      }
    }
    
    // If still not authenticated, redirect to login
    if (!authStore.isAuthenticated) {
      next('/login')
      return
    }
  }
  
  // If trying to access login while authenticated, redirect to dashboard
  if (to.name === 'Login' && authStore.isAuthenticated) {
    next('/')
    return
  }
  
  next()
})

export default router
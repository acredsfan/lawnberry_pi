import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
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
      path: '/rtk',
      name: 'RtkDiagnostics',
      component: () => import('@/views/RtkDiagnosticsView.vue'),
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
      path: '/docs',
      name: 'DocsHub',
      component: () => import('@/views/DocsHubView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mission-planner',
      name: 'MissionPlanner',
      component: () => import('@/views/MissionPlannerView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/power-history',
      name: 'PowerHistory',
      component: () => import('@/views/PowerHistoryView.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

type AuthGuardStore = Pick<
  ReturnType<typeof useAuthStore>,
  'isAuthenticated' | 'token' | 'validateSession' | 'bootstrapCloudflare' | 'clearSession'
>

export function createAuthNavigationGuard(
  resolveAuthStore: () => AuthGuardStore = useAuthStore,
) {
  let cloudflareBootstrapAttempted = false

  return async (to: RouteLocationNormalized) => {
    const authStore = resolveAuthStore()

    if (!authStore.isAuthenticated && authStore.token) {
      await authStore.validateSession()
    }

    if (!authStore.isAuthenticated && !cloudflareBootstrapAttempted) {
      cloudflareBootstrapAttempted = true
      await authStore.bootstrapCloudflare()
    }

    if (to.name === 'Login' && authStore.isAuthenticated) {
      return { path: '/' }
    }

    if (to.meta.requiresAuth && !authStore.isAuthenticated) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }

    return true
  }
}

const authNavigationGuard = createAuthNavigationGuard()

router.beforeEach(async (to, _from) => {
  try { (window as any).__TopProgress?.start() } catch {}
  return authNavigationGuard(to)
})

router.afterEach(() => {
  try { (window as any).__TopProgress?.done() } catch {}
})

export default router

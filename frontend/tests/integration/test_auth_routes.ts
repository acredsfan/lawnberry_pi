import { describe, it, expect, beforeEach } from 'vitest'
import { createRouter, createWebHistory } from 'vue-router'
import { setActivePinia, createPinia, defineStore } from 'pinia'

// Minimal views as route components
const Dashboard = { template: '<div>Dashboard</div>' }
const Login = { template: '<div>Login</div>' }

// Import router guard logic by creating a router instance similar to src/router/index.ts
function makeRouter(authStore: any) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'Dashboard', component: Dashboard, meta: { requiresAuth: true } },
      { path: '/login', name: 'Login', component: Login, meta: { requiresAuth: false } },
    ],
  })

  // Inline guard copied from app router logic
  router.beforeEach(async (to, from, next) => {
    // If route requires auth
    if (to.meta.requiresAuth) {
      if (!authStore.isAuthenticated && authStore.token) {
        try { await authStore.validateSession() } catch { await authStore.logout() }
      }
      if (!authStore.isAuthenticated) { next('/login'); return }
    }
    if (to.name === 'Login' && authStore.isAuthenticated) { next('/'); return }
    next()
  })

  return router
}

// Define a testing auth store
const useTestAuthStore = defineStore('auth', {
  state: () => ({
    user: null as any,
    token: null as string | null,
    tokenExpiry: null as number | null,
    isAuthenticated: false,
  }),
  actions: {
    async login() { this.isAuthenticated = true; this.token = 't'; return true },
    async logout() { this.isAuthenticated = false; this.token = null },
    async validateSession() { return this.isAuthenticated },
  },
})

describe('auth route guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('redirects to login when unauthenticated', async () => {
    const store = useTestAuthStore()
    store.isAuthenticated = false
    const router = makeRouter(store)

    try { await router.push('/') } catch (e) {
      // ignore navigation errors in test
    }
    expect(router.currentRoute.value.fullPath).toBe('/login')
  })

  it('allows dashboard when authenticated', async () => {
    const store = useTestAuthStore()
    store.isAuthenticated = true
    const router = makeRouter(store)

    await router.push('/')
    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('redirects to dashboard when accessing login while authenticated', async () => {
    const store = useTestAuthStore()
    store.isAuthenticated = true
    const router = makeRouter(store)

    await router.push('/login')
    expect(router.currentRoute.value.fullPath).toBe('/')
  })
})

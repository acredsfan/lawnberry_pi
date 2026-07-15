import { describe, it, expect } from 'vitest'
import { createRouter, createWebHistory } from 'vue-router'
import { createAuthNavigationGuard } from '../../src/router'

const Dashboard = { template: '<div>Dashboard</div>' }
const Login = { template: '<div>Login</div>' }

function makeStore(overrides: Record<string, unknown> = {}) {
  return {
    isAuthenticated: false,
    token: null as string | null,
    validateSession: async () => false,
    bootstrapCloudflare: async () => false,
    clearSession: () => undefined,
    ...overrides,
  }
}

function makeRouter(authStore: ReturnType<typeof makeStore>) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'Dashboard', component: Dashboard, meta: { requiresAuth: true } },
      { path: '/login', name: 'Login', component: Login, meta: { requiresAuth: false } },
    ],
  })
  router.beforeEach(createAuthNavigationGuard(() => authStore as any))
  return router
}

describe('production auth route guard', () => {
  it('attempts Cloudflare bootstrap before redirecting to local login', async () => {
    let bootstraps = 0
    const store = makeStore({
      bootstrapCloudflare: async () => {
        bootstraps += 1
        return false
      },
    })
    const router = makeRouter(store)

    await router.push('/')

    expect(bootstraps).toBe(1)
    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/')
  })

  it('enters the requested page when Cloudflare bootstrap succeeds', async () => {
    const store = makeStore()
    store.bootstrapCloudflare = async () => {
      store.isAuthenticated = true
      store.token = 'cloudflare-session'
      return true
    }
    const router = makeRouter(store)

    await router.push('/')

    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('bootstraps a direct login visit and leaves no password page visible', async () => {
    const store = makeStore()
    store.bootstrapCloudflare = async () => {
      store.isAuthenticated = true
      store.token = 'cloudflare-session'
      return true
    }
    const router = makeRouter(store)

    await router.push('/login')

    expect(router.currentRoute.value.fullPath).toBe('/')
  })
})

import { describe, it, expect, beforeEach, beforeAll, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { refreshAuthenticatedSession } from '@/services/authSessionCoordinator'

type RefreshResponse = {
  access_token: string
  token: string
  expires_in: number
}

const authApiMock = {
  login: vi.fn(),
  bootstrapCloudflare: vi.fn(),
  logout: vi.fn(),
  refresh: vi.fn(),
  getProfile: vi.fn(),
}

let useAuthStore: any
let useApiModule: any
let originalAuthApi: any

let storageData: Record<string, string> = {}
const localStorageMock = {
  getItem: vi.fn((key: string) => (key in storageData ? storageData[key] : null)),
  setItem: vi.fn((key: string, value: string) => {
    storageData[key] = value
  }),
  removeItem: vi.fn((key: string) => {
    delete storageData[key]
  }),
  clear: vi.fn(() => {
    storageData = {}
  }),
}

const resetLocalStorageState = () => {
  storageData = {}
  localStorageMock.getItem.mockClear()
  localStorageMock.setItem.mockClear()
  localStorageMock.removeItem.mockClear()
  localStorageMock.clear.mockClear()
}

const clearAuthApiMocks = () => {
  authApiMock.login.mockClear()
  authApiMock.bootstrapCloudflare.mockClear()
  authApiMock.logout.mockClear()
  authApiMock.refresh.mockClear()
  authApiMock.getProfile.mockClear()
}

beforeAll(async () => {
  globalThis.localStorage = localStorageMock as unknown as Storage
  useApiModule = await import('../../src/composables/useApi')
  originalAuthApi = { ...useApiModule.authApi }
  const module = await import('../../src/stores/auth')
  useAuthStore = module.useAuthStore
})

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2025-10-20T12:00:00Z'))
  resetLocalStorageState()
  clearAuthApiMocks()
  Object.assign(useApiModule.authApi, authApiMock)
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  Object.assign(useApiModule.authApi, originalAuthApi)
})

describe('auth store token refresh', () => {
  it('bootstraps one shared LawnBerry session from Cloudflare Access', async () => {
    const store = useAuthStore()
    authApiMock.bootstrapCloudflare.mockResolvedValue({
      access_token: 'cloudflare-session',
      token: 'cloudflare-session',
      expires_in: 3600,
      user: { id: 'cf-user', username: 'operator@example.com', role: 'operator' },
    })

    const [first, second] = await Promise.all([
      store.bootstrapCloudflare(),
      store.bootstrapCloudflare(),
    ])

    expect(first).toBe(true)
    expect(second).toBe(true)
    expect(authApiMock.bootstrapCloudflare).toHaveBeenCalledTimes(1)
    expect(store.isAuthenticated).toBe(true)
    expect(store.user.username).toBe('operator@example.com')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('auth_token', 'cloudflare-session')
    expect(authApiMock.refresh).not.toHaveBeenCalled()
  })

  it('treats an unavailable Cloudflare assertion as local-login fallback without refreshing', async () => {
    const store = useAuthStore()
    authApiMock.bootstrapCloudflare.mockRejectedValue({ response: { status: 401 } })

    expect(await store.bootstrapCloudflare()).toBe(false)
    expect(authApiMock.bootstrapCloudflare).toHaveBeenCalledTimes(1)
    expect(authApiMock.refresh).not.toHaveBeenCalled()
    expect(store.isAuthenticated).toBe(false)
  })

  it('coalesces concurrent token refresh calls', async () => {
    const store = useAuthStore()
    store.token = 'existing-token'
    store.tokenExpiry = Date.now() + 60_000
    let resolveRefresh: ((value: RefreshResponse) => void) | undefined
    authApiMock.refresh.mockReturnValue(new Promise<RefreshResponse>((resolve) => {
      resolveRefresh = resolve
    }))

    const first = store.refreshToken()
    const second = store.refreshToken()
    resolveRefresh?.({ access_token: 'new-token', token: 'new-token', expires_in: 3600 })

    expect(await first).toBe(true)
    expect(await second).toBe(true)
    expect(authApiMock.refresh).toHaveBeenCalledTimes(1)
  })

  it('shares refresh state with non-store API clients', async () => {
    const store = useAuthStore()
    store.token = 'existing-token'
    store.tokenExpiry = Date.now() + 60_000
    let resolveRefresh: ((value: RefreshResponse) => void) | undefined
    authApiMock.refresh.mockReturnValue(new Promise<RefreshResponse>((resolve) => {
      resolveRefresh = resolve
    }))

    const storeRefresh = store.refreshToken()
    const interceptorRefresh = refreshAuthenticatedSession()
    resolveRefresh?.({ access_token: 'coordinated-token', token: 'coordinated-token', expires_in: 3600 })

    expect(await storeRefresh).toBe(true)
    expect(await interceptorRefresh).toBe('coordinated-token')
    expect(store.token).toBe('coordinated-token')
    expect(authApiMock.refresh).toHaveBeenCalledTimes(1)
  })

  it('schedules a bounded refresh for a short-lived token', async () => {
    const store = useAuthStore()
    store.token = 'existing-token'
    store.tokenExpiry = Date.now() + 4 * 60 * 1000

    authApiMock.refresh.mockResolvedValue({
      access_token: 'new-token',
      token: 'new-token',
      expires_in: 3600,
    } as RefreshResponse)

    store.startTokenRefreshTimer()

    expect(authApiMock.refresh).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(119_999)
    expect(authApiMock.refresh).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(2)
    await Promise.resolve()

    expect(authApiMock.refresh).toHaveBeenCalledTimes(1)
    expect(store.token).toBe('new-token')
    expect(store.tokenExpiry).toBeGreaterThan(Date.now())
    expect(localStorageMock.setItem).toHaveBeenCalledWith('auth_token', 'new-token')
    expect(authApiMock.logout).not.toHaveBeenCalled()
  })

  it('settles a refresh that returns a two-minute token without recursive calls', async () => {
    const store = useAuthStore()
    store.token = 'existing-token'
    store.tokenExpiry = Date.now() + 60_000
    authApiMock.refresh.mockResolvedValue({
      access_token: 'short-token',
      token: 'short-token',
      expires_in: 120,
    } as RefreshResponse)

    await expect(store.refreshToken()).resolves.toBe(true)

    expect(authApiMock.refresh).toHaveBeenCalledTimes(1)
    expect(store.token).toBe('short-token')
    expect(vi.getTimerCount()).toBe(1)
  })

  it('schedules a future refresh when outside the immediate window', async () => {
    const store = useAuthStore()
    store.token = 'existing-token'
    store.tokenExpiry = Date.now() + 5 * 60 * 1000 + 2000

    authApiMock.refresh.mockResolvedValue({
      access_token: 'refreshed-token',
      token: 'refreshed-token',
      expires_in: 3600,
    } as RefreshResponse)

    await store.startTokenRefreshTimer()

    expect(authApiMock.refresh).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1999)
    expect(authApiMock.refresh).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(2)
    await Promise.resolve()

    expect(authApiMock.refresh).toHaveBeenCalledTimes(1)
    expect(store.token).toBe('refreshed-token')
  })

  it('rehydrates the stored user when a token already exists on reload', async () => {
    storageData = {
      auth_token: 'persisted-token',
      token_expiry: String(Date.now() + 60 * 60 * 1000),
      user_data: JSON.stringify({ id: 'u1', username: 'admin', role: 'admin' }),
    }

    const store = useAuthStore()

    expect(store.user).toEqual({ id: 'u1', username: 'admin', role: 'admin' })
    expect(store.isAuthenticated).toBe(true)
  })

  it('validates from storage without calling profile when cached auth is still valid', async () => {
    storageData = {
      auth_token: 'persisted-token',
      token_expiry: String(Date.now() + 60 * 60 * 1000),
      user_data: JSON.stringify({ id: 'u1', username: 'admin', role: 'admin' }),
    }

    const store = useAuthStore()
    authApiMock.getProfile.mockResolvedValue({ id: 'u1', username: 'admin', role: 'admin' })

    const valid = await store.validateSession()

    expect(valid).toBe(true)
    expect(authApiMock.getProfile).not.toHaveBeenCalled()
  })
})

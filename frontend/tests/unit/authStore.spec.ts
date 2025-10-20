import { describe, it, expect, beforeEach, beforeAll, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

type RefreshResponse = {
  access_token: string
  token: string
  expires_in: number
}

const authApiMock = {
  login: vi.fn(),
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
  it('refreshes immediately when expiry is within refresh window', async () => {
    const store = useAuthStore()
    store.token = 'existing-token'
    store.tokenExpiry = Date.now() + 4 * 60 * 1000

    authApiMock.refresh.mockResolvedValue({
      access_token: 'new-token',
      token: 'new-token',
      expires_in: 3600,
    } as RefreshResponse)

    await store.startTokenRefreshTimer()

    expect(authApiMock.refresh).toHaveBeenCalledTimes(1)
    expect(store.token).toBe('new-token')
    expect(store.tokenExpiry).toBeGreaterThan(Date.now())
    expect(localStorageMock.setItem).toHaveBeenCalledWith('auth_token', 'new-token')
    expect(authApiMock.logout).not.toHaveBeenCalled()
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
})

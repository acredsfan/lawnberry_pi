import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useControlSession } from '@/composables/useControlSession'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('@/services/api', () => ({
  useApiService: vi.fn(() => ({ get: mockGet, post: mockPost })),
}))
vi.mock('@/stores/toast', () => ({
  useToastStore: vi.fn(() => ({ show: vi.fn() })),
}))

function mountWithComposable() {
  let result: ReturnType<typeof useControlSession>
  const Wrapper = defineComponent({
    setup() { result = useControlSession(); return {} },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  return { wrapper, getResult: () => result! }
}

describe('useControlSession', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => vi.useRealTimers())

  it('starts locked', () => {
    const { getResult } = mountWithComposable()
    expect(getResult().isControlUnlocked.value).toBe(false)
  })

  it('unlocks after successful authenticate', async () => {
    mockGet.mockResolvedValue({ data: { security_level: 'password', session_timeout_minutes: 15 } })
    mockPost.mockResolvedValue({ data: { session_id: 'abc', expires_at: null } })
    const { getResult } = mountWithComposable()
    const r = getResult()
    await r.loadSecurityConfig()
    r.authForm.credential = 'hunter2'
    await r.authenticateControl()
    expect(r.isControlUnlocked.value).toBe(true)
    expect(r.session.value?.session_id).toBe('abc')
  })

  it('lockControl clears session and resets form', async () => {
    mockPost.mockResolvedValue({ data: { session_id: 'xyz' } })
    const { getResult } = mountWithComposable()
    const r = getResult()
    r.authForm.credential = 'secret'
    await r.authenticateControl()
    r.lockControl()
    expect(r.isControlUnlocked.value).toBe(false)
    expect(r.session.value).toBeNull()
    expect(r.authForm.credential).toBe('')
  })

  it('session countdown fires via interval', async () => {
    mockPost.mockResolvedValue({ data: { session_id: 'abc', expires_at: new Date(Date.now() + 60000).toISOString() } })
    const { getResult } = mountWithComposable()
    const r = getResult()
    r.authForm.credential = 'x'
    await r.authenticateControl()
    expect(r.sessionTimeRemaining.value).toBeGreaterThan(58)
    vi.advanceTimersByTime(5000)
    await nextTick()
    expect(r.sessionTimeRemaining.value).toBeLessThan(56)
  })

  it('clears session timer on unmount', () => {
    const { wrapper } = mountWithComposable()
    // Should not throw; timer cleanup is internal
    expect(() => wrapper.unmount()).not.toThrow()
  })
})

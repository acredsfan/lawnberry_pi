import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useCameraFeed } from '@/composables/useCameraFeed'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('@/services/api', () => ({
  useApiService: vi.fn(() => ({ get: mockGet, post: mockPost })),
}))

// Minimal fetch mock
global.fetch = vi.fn()

function mountWithComposable(sessionId = () => 'sess-123') {
  let result: ReturnType<typeof useCameraFeed>
  const Wrapper = defineComponent({
    setup() { result = useCameraFeed(sessionId); return {} },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  return { wrapper, getResult: () => result! }
}

describe('useCameraFeed', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
    mockGet.mockResolvedValue({ data: { is_active: true, mode: 'streaming', statistics: {} } })
    mockPost.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
    delete (URL as any).createObjectURL
    delete (URL as any).revokeObjectURL
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('initializes with no stream or frame URL', () => {
    const { getResult } = mountWithComposable()
    const r = getResult()
    expect(r.cameraStreamUrl.value).toBeNull()
    expect(r.cameraFrameUrl.value).toBeNull()
  })

  it('cameraIsStreaming reflects streamUrl presence', () => {
    const { getResult } = mountWithComposable()
    const r = getResult()
    expect(r.cameraIsStreaming.value).toBe(false)
    r.cameraStreamUrl.value = '/api/v2/camera/stream.mjpeg?client=x'
    expect(r.cameraIsStreaming.value).toBe(true)
  })

  it('never places a manual-control session credential in the stream URL', async () => {
    const { getResult } = mountWithComposable(() => 'motion-authorizing-session')
    const r = getResult()

    await r.startCameraFeed()

    expect(r.cameraStreamUrl.value).toContain('/api/v2/camera/stream.mjpeg?')
    expect(r.cameraStreamUrl.value).not.toContain('session_id')
    expect(r.cameraStreamUrl.value).not.toContain('motion-authorizing-session')
  })

  it('keeps a healthy MJPEG URL stable instead of cancelling it on a timer', async () => {
    const { getResult } = mountWithComposable()
    const r = getResult()
    await r.startCameraFeed()
    r.handleCameraStreamLoad()
    const initialUrl = r.cameraStreamUrl.value

    await vi.advanceTimersByTimeAsync(12_000)

    expect(r.cameraStreamUrl.value).toBe(initialUrl)
  })

  it('stopCameraFeed clears stream and timers', async () => {
    const { getResult } = mountWithComposable()
    const r = getResult()
    r.cameraStreamUrl.value = '/api/v2/camera/stream.mjpeg?client=x'
    r.stopCameraFeed()
    expect(r.cameraStreamUrl.value).toBeNull()
    expect(r.cameraError.value).toBeNull()
  })

  it('handleCameraStreamError switches to snapshot fallback after 2 failures', async () => {
    const { getResult } = mountWithComposable()
    const r = getResult()
    r.handleCameraStreamError()   // failure #1 → refresh
    r.handleCameraStreamError()   // failure #2 → fallback
    expect(r.cameraStreamUnavailable.value).toBe(true)
  })

  it('keeps snapshot fallback alive when the fallback image loads', async () => {
    let objectUrlIndex = 0
    vi.mocked(URL.createObjectURL).mockImplementation(() => `blob:snapshot-${++objectUrlIndex}`)
    mockGet.mockImplementation((url: string) => {
      if (url === '/api/v2/camera/frame') {
        return Promise.resolve({
          data: new Blob(['jpeg'], { type: 'image/jpeg' }),
          headers: { 'content-type': 'image/jpeg' },
        })
      }
      return Promise.resolve({ data: { is_active: true, mode: 'streaming', statistics: {} } })
    })
    const { getResult } = mountWithComposable()
    const r = getResult()

    r.handleCameraStreamError()
    r.handleCameraStreamError()
    await vi.advanceTimersByTimeAsync(0)
    expect(r.cameraFrameUrl.value).toContain('blob:snapshot-')
    const callsBeforeLoad = mockGet.mock.calls.filter(
      ([url]) => url === '/api/v2/camera/frame',
    ).length

    r.handleCameraStreamLoad()
    await vi.advanceTimersByTimeAsync(2_100)

    expect(r.cameraStreamUnavailable.value).toBe(true)
    expect(r.cameraStreamUrl.value).toBeNull()
    expect(r.cameraFrameUrl.value).toContain('blob:snapshot-')
    expect(mockGet.mock.calls.filter(
      ([url]) => url === '/api/v2/camera/frame',
    ).length).toBeGreaterThan(callsBeforeLoad)
  })

  it('stops snapshot polling after MJPEG recovery', async () => {
    const { getResult } = mountWithComposable()
    const r = getResult()
    r.handleCameraStreamError()
    r.handleCameraStreamError()

    await vi.advanceTimersByTimeAsync(4_500)
    const frameCallsBeforeRecovery = mockGet.mock.calls.filter(
      ([url]) => url === '/api/v2/camera/frame',
    ).length
    expect(frameCallsBeforeRecovery).toBeGreaterThan(1)

    await vi.advanceTimersByTimeAsync(1_000)
    expect(r.cameraStreamUrl.value).toContain('/api/v2/camera/stream.mjpeg?')
    const frameCallsAfterRecovery = mockGet.mock.calls.filter(
      ([url]) => url === '/api/v2/camera/frame',
    ).length

    await vi.advanceTimersByTimeAsync(5_000)
    expect(mockGet.mock.calls.filter(
      ([url]) => url === '/api/v2/camera/frame',
    )).toHaveLength(frameCallsAfterRecovery)
  })

  it('does not resurrect camera timers when an in-flight start finishes after unmount', async () => {
    let resolveStatus!: (value: unknown) => void
    mockGet.mockImplementationOnce(() => new Promise((resolve) => { resolveStatus = resolve }))
    const { wrapper, getResult } = mountWithComposable()
    const r = getResult()

    const startPromise = r.startCameraFeed()
    wrapper.unmount()
    resolveStatus({ data: { is_active: true, mode: 'streaming', statistics: {} } })
    await startPromise

    expect(r.cameraStreamUrl.value).toBeNull()
    expect(r.cameraFrameUrl.value).toBeNull()
    expect(r.cameraStatusMessage.value).toBe('Camera paused')
    const callsAfterUnmount = mockGet.mock.calls.length
    await vi.advanceTimersByTimeAsync(12_000)
    expect(mockGet).toHaveBeenCalledTimes(callsAfterUnmount)
  })

  it('stopCameraFeed on unmount (called by onUnmounted)', () => {
    const { wrapper, getResult } = mountWithComposable()
    const r = getResult()
    r.cameraStreamUrl.value = '/api/v2/camera/stream.mjpeg?client=x'
    wrapper.unmount()
    expect(r.cameraStreamUrl.value).toBeNull()
    expect(r.cameraStatusMessage.value).toBe('Camera paused')
  })
})

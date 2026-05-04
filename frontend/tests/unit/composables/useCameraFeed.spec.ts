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
    mockGet.mockResolvedValue({ data: { is_active: true, mode: 'streaming', statistics: {} } })
    mockPost.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
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

  it('stopCameraFeed on unmount (called by onUnmounted)', () => {
    const { wrapper, getResult } = mountWithComposable()
    const r = getResult()
    r.cameraStreamUrl.value = '/api/v2/camera/stream.mjpeg?client=x'
    wrapper.unmount()
    expect(r.cameraStreamUrl.value).toBeNull()
    expect(r.cameraStatusMessage.value).toBe('Camera paused')
  })
})

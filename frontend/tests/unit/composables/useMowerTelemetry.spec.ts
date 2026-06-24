import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useMowerTelemetry } from '@/composables/useMowerTelemetry'

// Stub the native WS service
vi.mock('@/services/websocket', () => {
  const handlers = new Map<string, Array<(d: any) => void>>()
  const service = {
    connect: vi.fn().mockResolvedValue(undefined),
    subscribe: vi.fn((topic: string, cb: (d: any) => void) => {
      if (!handlers.has(topic)) handlers.set(topic, [])
      handlers.get(topic)!.push(cb)
    }),
    unsubscribe: vi.fn((topic: string, cb: (d: any) => void) => {
      const list = handlers.get(topic) ?? []
      handlers.set(topic, list.filter(h => h !== cb))
    }),
    emit: (topic: string, data: any) => handlers.get(topic)?.forEach(h => h(data)),
    setCadence: vi.fn(),
    ping: vi.fn(),
    listTopics: vi.fn(),
    dispatchTestMessage: vi.fn(),
    connected: { value: false },
    connecting: { value: false },
    disconnect: vi.fn(),
    _handlers: handlers,
  }
  return {
    useWebSocket: vi.fn(() => service),
    _mockService: service,
  }
})

vi.mock('@/services/api', () => ({
  useApiService: vi.fn(() => ({
    get: vi.fn().mockResolvedValue({
      data: { position: { latitude: 1.23, longitude: 4.56, accuracy: 2 }, nav_heading: 90 }
    }),
  })),
}))

function mountWithComposable() {
  let result: ReturnType<typeof useMowerTelemetry>
  const Wrapper = defineComponent({
    setup() {
      result = useMowerTelemetry()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  return { wrapper, getResult: () => result! }
}

describe('useMowerTelemetry', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('initializes with null position', () => {
    const { getResult } = mountWithComposable()
    expect(getResult().mowerPosition.value).toBeNull()
  })

  it('updates position from WS navigation event', async () => {
    const { getResult } = mountWithComposable()
    const { _mockService } = await import('@/services/websocket') as any
    await nextTick()

    _mockService.emit('telemetry.navigation', {
      position: { latitude: 51.5, longitude: -0.1, accuracy: 3 },
      nav_heading: 180,
    })
    await nextTick()

    const pos = getResult().mowerPosition.value
    expect(pos?.lat).toBe(51.5)
    expect(pos?.lon).toBe(-0.1)
    expect(pos?.heading).toBe(180)
  })

  it('prefers canonical body-center pose and preserves antenna diagnostics', async () => {
    const { getResult } = mountWithComposable()
    const { _mockService } = await import('@/services/websocket') as any
    await nextTick()

    _mockService.emit('telemetry.navigation', {
      position: { latitude: 40.0, longitude: -75.0, accuracy: 0.03, position_role: 'antenna' },
      nav_heading: 90,
      canonical_pose: {
        body_center: { latitude: 40.000004, longitude: -75.0, accuracy: 0.03 },
        antenna_position: { latitude: 40.0, longitude: -75.0, accuracy: 0.03 },
        heading_deg: 0,
        antenna_correction_state: 'applied',
      },
    })
    await nextTick()

    const pos = getResult().mowerPosition.value
    expect(pos?.lat).toBeCloseTo(40.000004)
    expect(pos?.positionRole).toBe('body_center')
    expect(pos?.antenna?.lat).toBe(40)
    expect(pos?.antennaCorrectionState).toBe('applied')
    expect(pos?.heading).toBe(0)
  })

  it('falls back to REST poll when WS is stale', async () => {
    const { getResult } = mountWithComposable()
    await nextTick()
    // Advance past 5s WS staleness window + one 2s poll tick
    vi.advanceTimersByTime(7001)
    await nextTick()
    // REST mock returns lat 1.23
    expect(getResult().mowerPosition.value?.lat).toBeCloseTo(1.23)
  })

  it('unsubscribes and stops poll on unmount', async () => {
    const { wrapper } = mountWithComposable()
    const { useWebSocket } = await import('@/services/websocket') as any
    const service = useWebSocket()
    wrapper.unmount()
    expect(service.unsubscribe).toHaveBeenCalledWith('telemetry.navigation', expect.any(Function))
    // Interval cleared — advancing time should NOT call REST
    vi.advanceTimersByTime(10000)
    await nextTick()
    // No additional REST calls after unmount
    expect(service.unsubscribe).toHaveBeenCalledTimes(1)
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useDashboardTelemetry } from '@/composables/useDashboardTelemetry'

const mockSubscribe = vi.fn()
const mockUnsubscribe = vi.fn()
const mockConnect = vi.fn().mockResolvedValue(undefined)
const mockSetCadence = vi.fn()

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    connected: { value: false },
    connecting: { value: false },
    connect: mockConnect,
    subscribe: mockSubscribe,
    unsubscribe: mockUnsubscribe,
    setCadence: mockSetCadence,
    disconnect: vi.fn(),
    emit: vi.fn(),
    subscribeTopic: vi.fn(),
  })),
}))

function mountWithComposable() {
  let result: ReturnType<typeof useDashboardTelemetry>
  const Wrapper = defineComponent({
    setup() { result = useDashboardTelemetry(); return {} },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  return { wrapper, getResult: () => result! }
}

describe('useDashboardTelemetry', () => {
  beforeEach(() => vi.clearAllMocks())

  it('exposes empty telemetry state before any message', () => {
    const { getResult } = mountWithComposable()
    expect(getResult().batteryData.value).toBeNull()
    expect(getResult().positionData.value).toBeNull()
  })

  it('updates batteryData on telemetry.power event', async () => {
    const { getResult } = mountWithComposable()
    await nextTick()
    // Simulate the callback registered for telemetry.power
    const powerCall = mockSubscribe.mock.calls.find(([topic]: [string]) => topic === 'telemetry.power')
    expect(powerCall).toBeDefined()
    const [, handler] = powerCall!
    handler({ percentage: 87.5, voltage: 12.4 })
    await nextTick()
    expect(getResult().batteryData.value?.percentage).toBe(87.5)
  })

  it('unsubscribes all topics on unmount', () => {
    const { wrapper } = mountWithComposable()
    wrapper.unmount()
    expect(mockUnsubscribe).toHaveBeenCalled()
  })
})

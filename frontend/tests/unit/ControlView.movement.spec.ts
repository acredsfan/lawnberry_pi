// @ts-nocheck
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, defineComponent, h } from 'vue'
import ControlView from '@/views/ControlView.vue'
import apiClient from '@/services/api'

const controlStoreContainer: { current: any } = { current: null }

vi.mock('@/stores/control', () => ({
  useControlStore: () => controlStoreContainer.current,
}))

const toastStore = {
  show: vi.fn(),
}

vi.mock('@/stores/toast', () => ({
  useToastStore: () => toastStore,
}))

vi.mock('@/components/ui/VirtualJoystick.vue', () => {
  const stub = defineComponent({
    name: 'VirtualJoystickStub',
    emits: ['change', 'end'],
    methods: {
      triggerChange(payload: any) {
        this.$emit('change', payload)
      },
      triggerEnd() {
        this.$emit('end')
      },
      reset() {
        this.$emit('change', { x: 0, y: 0, magnitude: 0, active: false })
        this.$emit('end')
      },
      setVector(vector: { x: number; y: number }) {
        this.$emit('change', {
          ...vector,
          magnitude: Math.min(1, Math.hypot(vector.x, vector.y)),
          active: true,
        })
      },
    },
    render() {
      return h('div', { class: 'virtual-joystick-stub' })
    },
  })
  return { default: stub }
})

vi.mock('@/stores/preferences', () => {
  const unitSystem = ref<'metric' | 'imperial'>('metric')
  return {
    usePreferencesStore: () => ({
      unitSystem,
      ensureInitialized: vi.fn(),
      setUnitSystem: vi.fn(),
      syncWithServer: vi.fn(),
    }),
  }
})

function createMockControlStore() {
  return {
    lockout: false,
    lockoutReason: '',
    lockoutUntil: null,
    lastEcho: null,
    lastCommandEcho: null,
    lastCommandResult: null,
    remediationLink: '',
    isLoading: false,
    commandInProgress: false,
    robohatStatus: null,
    submitCommand: vi.fn().mockResolvedValue({ result: 'accepted' }),
    fetchRoboHATStatus: vi.fn().mockResolvedValue({ telemetry_source: 'simulated' }),
    initWebSocket: vi.fn(),
    cleanup: vi.fn(),
  }
}

async function mountControlView() {
  const wrapper = mount(ControlView)
  await flushPromises()
  wrapper.vm.session = { session_id: 'session-1' }
  wrapper.vm.isControlUnlocked = true
  await flushPromises()
  // Camera feed introduces timers that are unnecessary for unit tests; stop it immediately.
  wrapper.vm.stopCameraFeed()
  await flushPromises()
  return wrapper
}

describe('ControlView manual movement loop', () => {
  beforeEach(() => {
    controlStoreContainer.current = createMockControlStore()
    toastStore.show.mockReset()
    vi.useFakeTimers()
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    apiClient.get.mockImplementation((url: string) => {
      if (url.startsWith('/api/v2/camera')) {
        return Promise.resolve({ data: {} })
      }
      if (url === '/api/v2/settings/security') {
        return Promise.resolve({ data: { security_level: 'password', session_timeout_minutes: 15 } })
      }
      return Promise.resolve({ data: {} })
    })
    apiClient.post.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
    vi.useRealTimers()
    controlStoreContainer.current = null
  })

  it('streams drive commands while a direction control is held', async () => {
    const wrapper = await mountControlView()
    const store = controlStoreContainer.current
    const joystick = wrapper.findComponent({ name: 'VirtualJoystickStub' })

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()
    expect(store.submitCommand).toHaveBeenCalledTimes(1)
    const initialCall = store.submitCommand.mock.calls.at(0)
    expect(initialCall?.[1]?.reason).toBe('manual-joystick')

    await vi.advanceTimersByTimeAsync(220)
    await flushPromises()
    expect(store.submitCommand).toHaveBeenCalledTimes(2)

    joystick.vm.triggerEnd()
    await flushPromises()

    const joystickCalls = store.submitCommand.mock.calls.filter(call => call[1]?.reason === 'manual-joystick')
    expect(joystickCalls.length).toBeGreaterThanOrEqual(2)

    const lastCall = store.submitCommand.mock.calls.at(-1)!
    expect(lastCall[0]).toBe('drive')
    expect(lastCall[1]).toMatchObject({ vector: { linear: 0, angular: 0 }, reason: 'manual-stop' })

    wrapper.unmount()
  })

  it('stop button immediately queues a zero vector command', async () => {
    const wrapper = await mountControlView()
    const store = controlStoreContainer.current
    const joystick = wrapper.findComponent({ name: 'VirtualJoystickStub' })

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()
    store.submitCommand.mockClear()

    const stopButton = wrapper.find('.stop-button')
    await stopButton.trigger('click')
    await flushPromises()

    expect(store.submitCommand).toHaveBeenCalled()
    const stopCall = store.submitCommand.mock.calls.at(-1)!
    expect(stopCall[0]).toBe('drive')
    expect(stopCall[1]).toMatchObject({ vector: { linear: 0, angular: 0 }, reason: 'manual-stop' })

    joystick.vm.triggerEnd()
    wrapper.unmount()
  })
})

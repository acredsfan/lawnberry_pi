// @ts-nocheck
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, defineComponent, h, reactive, nextTick } from 'vue'
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
    props: {
      disabled: { type: Boolean, default: false },
    },
    emits: ['change', 'end'],
    methods: {
      triggerChange(payload: any) {
        if (this.disabled) return
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
        if (this.disabled) return
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
  const store = reactive({
    lockout: false,
    lockoutReason: '',
    lockoutUntil: null,
    lastEcho: null,
    lastCommandEcho: null,
    lastCommandResult: null,
    remediationLink: '',
    isLoading: false,
    commandInProgress: false,
    robohatStatus: { telemetry_source: 'simulated' },
    submitCommand: vi.fn().mockResolvedValue({ result: 'accepted' }),
    fetchRoboHATStatus: vi.fn().mockImplementation(async () => store.robohatStatus),
    initWebSocket: vi.fn(),
    cleanup: vi.fn(),
  })

  return store
}

interface MountOptions {
  unlock?: boolean
  keepCameraFeed?: boolean
}

async function mountControlView(options: MountOptions = {}) {
  const { unlock = true, keepCameraFeed = false } = options
  const wrapper = mount(ControlView)
  await flushPromises()
  wrapper.vm.session = { session_id: 'session-1' }
  if (unlock) {
    wrapper.vm.isControlUnlocked = true
    await flushPromises()
  }
  if (!keepCameraFeed) {
    wrapper.vm.stopCameraFeed()
    await flushPromises()
  }
  return wrapper
}

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

describe('ControlView manual movement loop', () => {
  it('streams drive commands while a direction control is held', async () => {
    const store = controlStoreContainer.current
    store.robohatStatus = {
      telemetry_source: 'hardware',
      serial_connected: true,
      motor_controller_ok: true,
      last_watchdog_echo: 'rc=disable',
    }
    const wrapper = await mountControlView()
    const joystick = wrapper.findComponent({ name: 'VirtualJoystickStub' })

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()
    expect(store.submitCommand).toHaveBeenCalledTimes(1)
    const initialCall = store.submitCommand.mock.calls.at(0)
    expect(initialCall?.[1]?.reason).toBe('manual-joystick')
    expect(initialCall?.[1]?.max_speed_limit).toBeCloseTo(0.5, 2)

    await vi.advanceTimersByTimeAsync(140)
    await flushPromises()
    expect(store.submitCommand).toHaveBeenCalledTimes(2)

    joystick.vm.triggerEnd()
    await flushPromises()

    const joystickCalls = store.submitCommand.mock.calls.filter(call => call[1]?.reason === 'manual-joystick')
    expect(joystickCalls.length).toBeGreaterThanOrEqual(2)

    const lastCall = store.submitCommand.mock.calls.at(-1)!
    expect(lastCall[0]).toBe('drive')
    expect(lastCall[1]).toMatchObject({ vector: { linear: 0, angular: 0 }, reason: 'manual-stop', max_speed_limit: 0.5 })

    wrapper.unmount()
  })

  it('stop button immediately queues a zero vector command', async () => {
    const store = controlStoreContainer.current
    store.robohatStatus = {
      telemetry_source: 'hardware',
      serial_connected: true,
      motor_controller_ok: true,
      last_watchdog_echo: 'rc=disable',
    }
    const wrapper = await mountControlView()
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
    expect(stopCall[1]).toMatchObject({ vector: { linear: 0, angular: 0 }, reason: 'manual-stop', max_speed_limit: 0.5 })

    joystick.vm.triggerEnd()
    wrapper.unmount()
  })

  it('surfaces controller disconnects and blocks movement until the controller recovers', async () => {
    const store = controlStoreContainer.current
    store.robohatStatus = {
      telemetry_source: 'hardware',
      serial_connected: true,
      motor_controller_ok: true,
      last_watchdog_echo: 'rc=disable',
    }

    const wrapper = await mountControlView()
    const joystick = wrapper.findComponent({ name: 'VirtualJoystickStub' })

    expect(wrapper.find('.controller-chip__value').text()).toBe('Ready')

    store.submitCommand.mockClear()
    toastStore.show.mockClear()

    store.robohatStatus = {
      ...store.robohatStatus,
      serial_connected: false,
      motor_controller_ok: false,
      last_watchdog_echo: null,
    }
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.controller-chip__value').text()).toBe('Disconnected')
    expect(wrapper.text()).toContain('Motor controller USB link not detected. Check cabling and power.')
    expect(toastStore.show).toHaveBeenCalledWith('Motor controller disconnected', 'error', 4000)

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()

    expect(store.submitCommand).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Motor controller USB link not detected. Check cabling and power.')

    toastStore.show.mockClear()

    store.robohatStatus = {
      telemetry_source: 'hardware',
      serial_connected: true,
      motor_controller_ok: true,
      last_watchdog_echo: 'rc=disable',
    }
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.controller-chip__value').text()).toBe('Ready')
    expect(toastStore.show.mock.calls).toContainEqual(['Motor controller connected', 'success', 2500])
    expect(toastStore.show.mock.calls).toContainEqual(['Motor controller ready', 'success', 2500])

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()

    expect(store.submitCommand).toHaveBeenCalledTimes(1)

    joystick.vm.triggerEnd()
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps joystick movement blocked until the controller is ready', async () => {
    const store = controlStoreContainer.current
    store.robohatStatus = {
      telemetry_source: 'hardware',
      serial_connected: true,
      motor_controller_ok: false,
      last_error: 'usb_control_unavailable',
      last_watchdog_echo: null,
    }

    const wrapper = await mountControlView()
    const joystick = wrapper.findComponent({ name: 'VirtualJoystickStub' })

    expect(wrapper.find('.controller-chip__value').text()).toBe('Handshake pending')

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()

    expect(store.submitCommand).not.toHaveBeenCalled()

    store.robohatStatus = {
      telemetry_source: 'hardware',
      serial_connected: true,
      motor_controller_ok: true,
      last_watchdog_echo: 'rc=disable',
      last_error: null,
    }
    await nextTick()
    await flushPromises()

    joystick.vm.triggerChange({ x: 0, y: 1, magnitude: 1, active: true })
    await flushPromises()

    expect(store.submitCommand).toHaveBeenCalledTimes(1)

    joystick.vm.triggerEnd()
    await flushPromises()
    wrapper.unmount()
  })
})

describe('ControlView camera stream recovery', () => {
  it('restores manual control from an existing authenticated session without prompting for password again', async () => {
    apiClient.get.mockImplementation((url: string) => {
      if (url === '/api/v2/settings/security') {
        return Promise.resolve({ data: { security_level: 'password', session_timeout_minutes: 15 } })
      }
      if (url === '/api/v2/control/manual-unlock/status') {
        return Promise.resolve({ data: { authorized: true, session_id: 'restored-session', expires_at: new Date(Date.now() + 60_000).toISOString(), source: 'bearer_token' } })
      }
      if (url.startsWith('/api/v2/camera')) {
        return Promise.resolve({ data: {} })
      }
      return Promise.resolve({ data: {} })
    })

    const wrapper = mount(ControlView)
    await flushPromises()

    expect(wrapper.vm.isControlUnlocked).toBe(true)
    expect(wrapper.vm.session).toMatchObject({ session_id: 'restored-session' })
    expect(wrapper.find('.control-interface').exists()).toBe(true)

    wrapper.unmount()
  })

  it('retries MJPEG streaming after entering snapshot fallback', async () => {
    const wrapper = await mountControlView({ unlock: false, keepCameraFeed: true })
    const vm = wrapper.vm as any

    apiClient.get.mockImplementation((url: string) => {
      if (url === '/api/v2/camera/status') {
        return Promise.resolve({
          data: {
            initialized: true,
            streaming: true,
            sim_mode: false,
            statistics: { fps: 12 },
          },
        })
      }
      if (url === '/api/v2/camera/frame') {
        return Promise.resolve({
          data: {
            frame_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
            capture_ts: new Date().toISOString(),
          },
        })
      }
      return Promise.resolve({ data: {} })
    })

    vm.cameraStreamFailureCount = 1
    vm.cameraStreamUnavailable = false
    vm.cameraStreamUrl = '/api/v2/camera/stream.mjpeg?client=test'

    vm.handleCameraStreamError()
    await flushPromises()

    expect(vm.cameraStreamUnavailable).toBe(true)
    expect(vm.cameraModeBadge.label).toBe('SNAPSHOT FALLBACK')
    vm.cameraInfo.active = true

    await vm.attemptCameraStreamRecovery()
    await flushPromises()

    expect(vm.cameraStreamUnavailable).toBe(false)
    expect(vm.cameraStreamUrl).toMatch(/\/api\/v2\/camera\/stream\.mjpeg/)
    expect(vm.cameraStreamFailureCount).toBe(0)

    vm.stopCameraFeed()
    wrapper.unmount()
  })

  it('replaces placeholder system controls with real backend control actions', async () => {
    const wrapper = await mountControlView()

    apiClient.post.mockImplementation((url: string) => {
      if (url === '/api/v2/control/pause') {
        return Promise.resolve({ data: { status: 'paused' } })
      }
      if (url === '/api/v2/control/resume') {
        return Promise.resolve({ data: { status: 'running' } })
      }
      if (url === '/api/v2/control/return-home') {
        return Promise.resolve({ data: { status: 'returning_home' } })
      }
      return Promise.resolve({ data: {} })
    })

    const buttons = wrapper.findAll('.system-controls .btn')
    expect(buttons).toHaveLength(3)

    await buttons[0].trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/api/v2/control/return-home', {})
    expect(wrapper.text()).toContain('Return-to-base sequence started')

    await buttons[1].trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/api/v2/control/pause', {})
    expect(wrapper.text()).toContain('System paused')

    await buttons[2].trigger('click')
    await flushPromises()
    expect(apiClient.post).toHaveBeenCalledWith('/api/v2/control/resume', {})
    expect(wrapper.text()).toContain('System resumed')

    wrapper.unmount()
  })
})

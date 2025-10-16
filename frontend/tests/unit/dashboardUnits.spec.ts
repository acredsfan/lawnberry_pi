import { describe, it, beforeEach, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia, storeToRefs } from 'pinia'

// Mock API modules first, before importing components
vi.mock('@/composables/useApi', () => ({
  systemApi: {
    getStatus: vi.fn(),
  },
  controlApi: {
    start: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn().mockResolvedValue(undefined),
    emergencyStop: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
    getStatus: vi.fn().mockResolvedValue(undefined),
  },
  telemetryApi: {
    getCurrent: vi.fn(),
  },
  weatherApi: {
    getCurrent: vi.fn(),
  },
  settingsApi: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    resetToDefaults: vi.fn(),
  },
  maintenanceApi: {
    getImuCalibrationStatus: vi.fn(),
    runImuCalibration: vi.fn(),
  },
}))

vi.mock('@/services/websocket', () => ({
  useWebSocket: () => {
    const connected = ref(false)
    const connecting = ref(false)
    return {
      connected,
      connecting,
      connect: vi.fn(async () => {
        connected.value = true
      }),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      setCadence: vi.fn(),
    }
  },
}))

// Import after mocking
import DashboardView from '@/views/DashboardView.vue'
import { usePreferencesStore } from '@/stores/preferences'
import { systemApi, controlApi, telemetryApi, weatherApi, settingsApi, maintenanceApi } from '@/composables/useApi'

// Create telemetry factory function
const createTelemetryPayload = () => ({
  battery: { percentage: 55.5, voltage: 12.4 },
  position: {
    latitude: 37.123456,
    longitude: -122.123456,
    accuracy: 1.2,
    hdop: 0.8,
    satellites: 12,
    speed: 1.5,
    rtk_status: 'fix',
  },
  environmental: {
    temperature_c: 22,
    humidity_percent: 45,
    pressure_hpa: 1012,
    altitude_m: 10,
  },
  tof: {
    left: { distance_mm: 1200, range_status: 'valid', signal_strength: 200 },
    right: { distance_mm: 1300, range_status: 'valid', signal_strength: 210 },
  },
  imu: {
    calibration: 2,
    calibration_status: 'calibrated',
  },
  motor_status: 'idle',
  source: 'hardware',
})

const defaultSystemStatus = { status: 'Active', uptime: '1h 0m' }

describe('DashboardView unit preferences', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(systemApi.getStatus).mockResolvedValue(defaultSystemStatus)
    vi.mocked(telemetryApi.getCurrent).mockResolvedValue(createTelemetryPayload())
    vi.mocked(weatherApi.getCurrent).mockResolvedValue({})
    vi.mocked(maintenanceApi.getImuCalibrationStatus).mockResolvedValue({ in_progress: false, last_result: null })
    vi.mocked(maintenanceApi.runImuCalibration).mockResolvedValue({
      calibration_score: 3,
      calibration_status: 'calibrated',
      status: 'completed',
      timestamp: new Date().toISOString(),
      steps: [],
    })
  })

  it('updates unit-dependent computed values when preference changes', async () => {
    vi.mocked(settingsApi.getSettings).mockResolvedValue({ system: { unit_system: 'metric' } })
    const pinia = createPinia()
    setActivePinia(pinia)

    const wrapper = mount(DashboardView, {
      global: {
        plugins: [pinia],
      },
    })

    await flushPromises()

    const preferences = usePreferencesStore()

    expect(wrapper.vm.speedUnit).toBe('m/s')
    expect(wrapper.vm.temperatureUnit).toBe('°C')
    expect(wrapper.vm.altitudeUnit).toBe('m')
    expect(wrapper.vm.pressureUnit).toBe('hPa')
    expect(wrapper.vm.tofUnit).toBe('cm')
    expect(wrapper.vm.speedDisplay).toBe('1.5')
    expect(wrapper.vm.temperatureDisplay).toBe('22.0')
    expect(wrapper.vm.altitudeDisplay).toBe('10.0')
    expect(wrapper.vm.pressureDisplay).toBe('1012.0')
    expect(wrapper.vm.tofLeftDisplay).toBe('120.0')

    preferences.setUnitSystem('imperial')
    await nextTick()
    await nextTick()

    expect(wrapper.vm.speedUnit).toBe('mph')
    expect(wrapper.vm.temperatureUnit).toBe('°F')
    expect(wrapper.vm.altitudeUnit).toBe('ft')
    expect(wrapper.vm.pressureUnit).toBe('inHg')
    expect(wrapper.vm.tofUnit).toBe('in')
    expect(wrapper.vm.speedDisplay).toBe('3.4')
    expect(wrapper.vm.temperatureDisplay).toBe('71.6')
    expect(wrapper.vm.altitudeDisplay).toBe('32.8')
    expect(wrapper.vm.pressureDisplay).toBe('29.88')
    expect(wrapper.vm.tofLeftDisplay).toBe('47.2')

    wrapper.unmount()
  })

  it('applies imperial preference from settings API on load', async () => {
    vi.mocked(settingsApi.getSettings).mockResolvedValue({ system: { unit_system: 'imperial' } })
    const pinia = createPinia()
    setActivePinia(pinia)

    const wrapper = mount(DashboardView, {
      global: {
        plugins: [pinia],
      },
    })

    await flushPromises()

  const preferences = usePreferencesStore()
  const { unitSystem } = storeToRefs(preferences)
  expect(unitSystem.value).toBe('imperial')
    expect(wrapper.vm.speedUnit).toBe('mph')
    expect(wrapper.vm.temperatureUnit).toBe('°F')
    expect(wrapper.vm.altitudeUnit).toBe('ft')
    expect(wrapper.vm.pressureUnit).toBe('inHg')
    expect(wrapper.vm.tofUnit).toBe('in')

    wrapper.unmount()
  })
})

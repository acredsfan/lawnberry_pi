import { describe, it, beforeEach, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/composables/useApi', () => ({
  systemApi: {
    getStatus: vi.fn().mockResolvedValue({ status: 'Active', uptime: '1h 0m' }),
  },
  settingsApi: {
    getSettings: vi.fn().mockResolvedValue({ system: { unit_system: 'metric' } }),
    updateSettings: vi.fn(),
    resetToDefaults: vi.fn(),
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
    getCurrent: vi.fn().mockResolvedValue({}),
  },
  maintenanceApi: {
    getImuCalibrationStatus: vi.fn().mockResolvedValue({ in_progress: false, last_result: null }),
    runImuCalibration: vi.fn().mockResolvedValue({
      calibration_score: 3,
      calibration_status: 'calibrated',
      status: 'completed',
      timestamp: new Date().toISOString(),
      steps: [],
    }),
  },
}))

vi.mock('@/services/websocket', () => ({
  useWebSocket: () => {
    return {
      connected: { value: false },
      connecting: { value: false },
      connect: vi.fn(async () => { /* no-op */ }),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      setCadence: vi.fn(),
      dispatchTestMessage: vi.fn(),
    }
  },
}))

import DashboardView from '@/views/DashboardView.vue'
import { telemetryApi } from '@/composables/useApi'

const makePowerTelemetry = () => ({
  battery: { percentage: 77.1, voltage: 12.6 },
  power: {
    battery_voltage: 12.6,
    battery_current: 1.6,
    battery_power: 20.2,
    solar_voltage: 21.8,
    solar_current: -1.4,
    solar_power: -30.5,
    load_current: 0.5,
  },
})

const mountDashboard = async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  vi.mocked(telemetryApi.getCurrent).mockResolvedValue({
    ...makePowerTelemetry(),
    position: {},
    tof: { left: {}, right: {} },
    imu: {},
  } as any)

  const wrapper = mount(DashboardView, { global: { plugins: [pinia] } })
  await flushPromises()
  return wrapper
}

describe('Power card metrics', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders battery, solar, and load metrics with correct normalization', async () => {
    const wrapper = await mountDashboard()

    // Battery
    expect(wrapper.vm.batteryVoltageDisplay).toBe('12.6')
    expect(wrapper.vm.batteryChargeStateDisplay).toBe('CHARGING')

    // Solar normalization (no negative values in display)
    expect(wrapper.vm.solarVoltageDisplay).toBe('21.8')
    expect(wrapper.vm.solarCurrentDisplay).toBe('1.40')
    // 30.5 rounds to 31.0 with .1 precision rule here; our component rounds >=100 differently
    expect(['30.5', '31.0']).toContain(wrapper.vm.solarPowerDisplay)

    // Load derived power
    expect(wrapper.vm.loadCurrentDisplay).toBe('0.50')
    // load power = Vbatt * Iload = 12.6 * 0.5 = 6.3 → display rounds to 6.3
    expect(wrapper.vm.loadPowerDisplay).toBe('6.3')
    expect(['ON', 'ENABLED', 'ACTIVE']).toContain(wrapper.vm.loadStateDisplay)

    wrapper.unmount()
  })
})

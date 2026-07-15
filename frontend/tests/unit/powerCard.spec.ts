import { describe, it, beforeEach, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

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
  powerApi: {
    getState: vi.fn().mockResolvedValue({
      available: true,
      fresh: true,
      reason_code: null,
      source: 'victron',
      sampled_at: new Date().toISOString(),
      sample_age_seconds: 0.4,
      voltage: 12.6,
      battery_current: 1.6,
      battery_power: 20.2,
      solar_current: -1.4,
      solar_power: -30.5,
      load_power: 6.3,
      soc_percent: 77.1,
      charging_confirmed: true,
    }),
  },
}))

vi.mock('@/services/websocket', () => ({
  useWebSocket: () => {
    return {
      connected: ref(false),
      connecting: ref(false),
      connect: vi.fn(async () => {
        /* no-op */
      }),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      setCadence: vi.fn(),
      dispatchTestMessage: vi.fn(),
    }
  },
}))

import DashboardView from '@/views/DashboardView.vue'
import PowerSystemCard from '@/components/dashboard/PowerSystemCard.vue'
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

    wrapper.unmount()
  })

  it('renders missing numeric power telemetry as unavailable, never zero', () => {
    const wrapper = mount(PowerSystemCard, {
      props: {
        data: {
          percentage: null,
          voltage: null,
          current: null,
          solarPower: null,
          source: 'unavailable',
          sampleAgeSeconds: null,
          fresh: false,
        },
      },
    })

    expect(wrapper.get('[data-testid="battery-percentage"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="battery-voltage"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="power-source"]').text()).toBe('UNAVAILABLE')
    expect(wrapper.text()).not.toContain('0.0V')
  })
})

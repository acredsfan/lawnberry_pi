import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp } from './utils/test-setup'

test.describe('Dashboard telemetry', () => {
  test('streams live updates via mocked WebSocket', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend)

    await expect
      .poll(async () => page.evaluate(() => typeof (window as any).__APP_TEST_HOOKS__?.emitTelemetryMessage))
      .toBe('function')

    await expect
      .poll(async () => page.evaluate(() => Boolean((window as any).__APP_TEST_HOOKS__?.telemetrySubscriptionsReady)))
      .toBeTruthy()

    const battery = page.getByTestId('battery-percentage')
    await expect(battery).toHaveText('87.5%')

    await page.evaluate(() => {
      const emit = (window as any).__APP_TEST_HOOKS__?.emitTelemetryMessage
      if (!emit) throw new Error('emitTelemetryMessage not available')
      emit({
        event: 'telemetry.data',
        topic: 'telemetry.power',
        data: {
          battery: { percentage: 63.2, voltage: 12.1 },
          solar: { power: 142.4, voltage: 27.9, current: 5.2 },
        },
      })
      emit({
        event: 'telemetry.data',
        topic: 'telemetry.environmental',
        data: {
          environmental: {
            temperature_c: 29.5,
            humidity_percent: 61.2,
            pressure_hpa: 1009.2,
            altitude_m: 22.3,
          },
        },
      })
    })

    await expect
      .poll(async () => (await battery.textContent())?.trim())
      .toBe('63.2%')

    await expect(page.getByTestId('temperature-value')).toContainText('29.5')
    await expect(page.getByTestId('humidity-value')).toContainText('61.2')
    await expect(page.getByTestId('pressure-value')).toContainText('1009.2')
  })

  test('highlights degraded GPS accuracy', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend)

    await expect
      .poll(async () => page.evaluate(() => typeof (window as any).__APP_TEST_HOOKS__?.emitTelemetryMessage))
      .toBe('function')

    await expect
      .poll(async () => page.evaluate(() => Boolean((window as any).__APP_TEST_HOOKS__?.telemetrySubscriptionsReady)))
      .toBeTruthy()

    const gpsStatus = page.getByTestId('gps-status')
    await expect(gpsStatus).toHaveText(/Accuracy ±0.70 m/)

    await page.evaluate(() => {
      const emit = (window as any).__APP_TEST_HOOKS__?.emitTelemetryMessage
      if (!emit) throw new Error('emitTelemetryMessage not available')
      emit({
        event: 'telemetry.data',
        topic: 'telemetry.navigation',
        data: {
          position: {
            latitude: 37.775,
            longitude: -122.4194,
            accuracy: 4.3,
            hdop: 3.2,
            satellites: 6,
            rtk_status: null,
          },
        },
      })
    })

    await expect
      .poll(async () => (await gpsStatus.textContent())?.trim())
      .toMatch(/Accuracy ±4\.30 m/)

    const speedValue = page.getByTestId('speed-value')
    await expect(speedValue).toContainText('0.6')
  })

  test('renders hardware sensor snapshots for diagnostics', async ({ page }) => {
    const backend = new MockBackend()
    backend.setHardwareSnapshot({
      telemetry_source: 'hardware',
      battery: { percentage: 78.8, voltage: 12.3 },
      position: { latitude: 37.7751, longitude: -122.4192 },
      velocity: { linear: { x: 0.82 } },
      safety_state: 'nominal',
    })
    backend.setTelemetry({
      battery: { percentage: 78.8, voltage: 12.3 },
      position: { latitude: 37.7751, longitude: -122.4192, speed: 0.82 },
    })

    await launchApp(page, backend)

    await expect
      .poll(async () => page.evaluate(() => typeof (window as any).__APP_TEST_HOOKS__?.emitTelemetryMessage))
      .toBe('function')

    await expect
      .poll(async () => page.evaluate(() => Boolean((window as any).__APP_TEST_HOOKS__?.telemetrySubscriptionsReady)))
      .toBeTruthy()

    await page.evaluate(() => {
      const emit = (window as any).__APP_TEST_HOOKS__?.emitTelemetryMessage
      if (!emit) throw new Error('emitTelemetryMessage not available')
      emit({
        event: 'telemetry.data',
        topic: 'telemetry.sensors',
        data: {
          imu: { calibration: 2, calibration_status: 'warning' },
          tof: {
            left: { distance_mm: 280, status: 'valid' },
            right: { distance_mm: 140, status: 'wrap_around' },
          },
        },
      })
    })

    await expect(page.getByTestId('battery-percentage')).toHaveText('78.8%')
    await expect(page.getByTestId('speed-value')).toContainText('0.8')
    await expect(page.getByTestId('battery-voltage')).toHaveText('12.3V')
  })
})

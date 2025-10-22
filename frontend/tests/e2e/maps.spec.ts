import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('Mapping workflow', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('adds and persists synthetic zone via harness helpers', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/maps')

    const harnessCard = page.getByTestId('e2e-map-tools')
    await expect(harnessCard).toBeVisible()

    await expect
      .poll(() =>
        page.evaluate(() => {
          const store = (window as any).__APP_TEST_HOOKS__?.mapStore
          return store?.configuration ? 1 : 0
        }),
      )
      .toBeGreaterThan(0)

    await page.getByTestId('e2e-add-mowing-zone').click()

    await expect
      .poll(() =>
        page.evaluate(() => {
          const store = (window as any).__APP_TEST_HOOKS__?.mapStore
          return store?.configuration?.mowing_zones?.length ?? 0
        }),
      )
      .toBeGreaterThan(0)

    await page.getByTestId('e2e-save-map').click()

    await expect
      .poll(() => backend.getRequests().filter((entry) => entry.method === 'PUT' && entry.path === '/api/v2/map/configuration').length)
      .toBeGreaterThan(0)

    await expect
      .poll(() => backend.lastSavedConfiguration?.zones?.filter((zone: any) => zone.zone_type === 'mow').length ?? 0)
      .toBeGreaterThan(0)

    const mowingZone = backend.lastSavedConfiguration?.zones?.find((zone: any) => zone.zone_type === 'mow')
    expect(mowingZone).toBeTruthy()
    const coordinates = mowingZone?.geometry?.coordinates?.[0]
    expect(Array.isArray(coordinates)).toBe(true)
    expect(coordinates?.length).toBeGreaterThanOrEqual(4)

    await page.waitForFunction(() => {
      const store = (window as any).__APP_TEST_HOOKS__?.mapStore
      return Array.isArray(store?.configuration?.mowing_zones) && store.configuration.mowing_zones.length > 0
    })

    const zoneCount = await page.evaluate(() => {
      const store = (window as any).__APP_TEST_HOOKS__?.mapStore
      return store?.configuration?.mowing_zones?.length ?? 0
    })

    expect(zoneCount).toBeGreaterThan(0)
  })
})

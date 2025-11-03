import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

const MAP_CONTAINER_SELECTOR = '.mission-planner-view .map-container'


test.describe('Mission planner map rendering', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  for (const scenario of [
    { name: 'OSM provider', settings: { provider: 'osm', style: 'standard' } },
    { name: 'Google provider with API key', settings: { provider: 'google', style: 'satellite', google_api_key: 'TEST_KEY' } },
  ]) {
    test(`displays tiles for ${scenario.name}`, async ({ page }) => {
      const backend = new MockBackend()
      backend.setMapSettings(scenario.settings)

      await launchApp(page, backend, '/mission-planner')

      await expect(page.locator(MAP_CONTAINER_SELECTOR)).toBeVisible()

      await expect
        .poll(async () => {
          return await page.evaluate((selector) => {
            const container = document.querySelector(selector)
            if (!container) return { hasPane: false, tileCount: 0 }
            const pane = container.querySelector('.leaflet-pane')
            const tiles = container.querySelectorAll('img.leaflet-tile-loaded')
            return { hasPane: Boolean(pane), tileCount: tiles.length }
          }, MAP_CONTAINER_SELECTOR)
        }, {
          message: 'Leaflet map should initialize and load tiles',
          timeout: 8000,
        })
        .toMatchObject({ hasPane: true })
    })
  }

  test('map loads after navigating from dashboard', async ({ page }) => {
    const backend = new MockBackend()
    backend.setMapSettings({ provider: 'osm', style: 'standard' })

    await launchApp(page, backend, '/')

    await page.getByRole('link', { name: 'Mission Planner' }).click()

    await expect(page.locator(MAP_CONTAINER_SELECTOR)).toBeVisible()

    await expect
      .poll(async () => {
        return await page.evaluate((selector) => {
          const container = document.querySelector(selector)
          if (!container) return { hasPane: false, tileCount: 0 }
          const pane = container.querySelector('.leaflet-pane')
          const tiles = container.querySelectorAll('img.leaflet-tile-loaded')
          return { hasPane: Boolean(pane), tileCount: tiles.length }
        }, MAP_CONTAINER_SELECTOR)
      }, {
        message: 'Leaflet map should initialize and load tiles after navigation',
        timeout: 8000,
      })
      .toMatchObject({ hasPane: true })
  })
})

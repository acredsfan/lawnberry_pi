import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('Map provider fallback', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('requests backend fallback and switches to OSM provider', async ({ page }) => {
    const backend = new MockBackend()
    backend.setMapSettings({ provider: 'google' })
    backend.setMapConfiguration({ provider: 'google_maps' })

    await launchApp(page, backend, '/maps')

    await page.evaluate(async () => {
      const store = (window as any).__APP_TEST_HOOKS__?.mapStore
      await store?.triggerProviderFallback()
      return store?.providerFallbackActive
    })

    await expect
      .poll(() => backend.getRequests().filter((entry) => entry.method === 'POST' && entry.path === '/api/v2/map/provider-fallback').length)
      .toBeGreaterThan(0)

    const fallbackRequest = backend
      .getRequests()
      .find((entry) => entry.method === 'POST' && entry.path === '/api/v2/map/provider-fallback')
    expect(fallbackRequest).toBeTruthy()

    await expect
      .poll(async () => {
        return await page.evaluate(() => {
          const store = (window as any).__APP_TEST_HOOKS__?.mapStore
          return store?.configuration?.provider
        })
      })
      .toBe('osm')
  })
})

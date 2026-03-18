import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('Mission recovery visibility', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('shows recovered paused mission detail and waypoint progress', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/mission-planner')

    await page.evaluate(() => {
      const hooks = (window as any).__APP_TEST_HOOKS__
      const store = hooks?.missionStore
      if (!store) return

      store.currentMission = {
        id: 'mission-1',
        name: 'Recovery Test Mission',
        waypoints: [
          { id: 'wp-1', lat: 51.5, lon: -0.09, blade_on: false, speed: 50 },
          { id: 'wp-2', lat: 51.5005, lon: -0.091, blade_on: false, speed: 50 },
        ],
        created_at: '2026-03-16T00:00:00Z',
      }
      store.missionStatus = 'paused'
      store.progress = 50
      store.currentWaypointIndex = 1
      store.totalWaypoints = 2
      store.statusDetail = 'Recovered after backend restart; explicit operator resume required'
    })

    await expect.poll(() => page.evaluate(() => {
      return (window as any).__APP_TEST_HOOKS__?.missionStore?.missionStatus
    })).toBe('paused')

    await expect(page.getByText('Paused (recovered)')).toBeVisible()
    await expect(page.getByText('Recovered after backend restart; explicit operator resume required')).toBeVisible()
    await expect(page.getByText('Waypoint: 2 of 2')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Resume' })).toBeEnabled()
  })
})
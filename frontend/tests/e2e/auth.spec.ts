import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('Authentication flow', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('allows valid credentials to reach the dashboard', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/login', { auth: false })

    await page.getByLabel('Operator credential').fill('operator-test-credential')
    await page.getByRole('button', { name: 'Sign In' }).click()

    await expect(page).toHaveURL('/')
    await expect(page.getByText('SYSTEM DASHBOARD')).toBeVisible()

    const token = await page.evaluate(() => window.localStorage.getItem('auth_token'))
    expect(token).toBe('test-token')
  })

  test('does not advertise a known default password', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/login', { auth: false })

    await expect(page.getByText('LawnBerry has no default password.')).toBeVisible()
    await expect(page.getByText(/admin \/ admin/i)).toHaveCount(0)
  })
})

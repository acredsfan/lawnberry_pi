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

    await page.getByLabel('Username').fill('admin')
    await page.getByLabel('Password').fill('admin')
    await page.getByRole('button', { name: 'Sign In' }).click()

    await expect(page).toHaveURL('/')
    await expect(page.getByText('SYSTEM DASHBOARD')).toBeVisible()

    const token = await page.evaluate(() => window.localStorage.getItem('auth_token'))
    expect(token).toBe('test-token')
  })
})

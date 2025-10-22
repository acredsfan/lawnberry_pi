import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('Manual control access', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('requires unlock and supports emergency stop workflow', async ({ page }) => {
    const backend = new MockBackend()
    backend.setWebSocketScript([{ message: { event: 'connection.established', client_id: 'control-client' } }])

    await launchApp(page, backend, '/control')

    await expect(page.getByText('Control Access Required')).toBeVisible()
    await page.getByLabel('Confirm Password').fill('admin')
    await page.getByRole('button', { name: 'Unlock Control' }).click()

    const emergencyButton = page.getByRole('button', { name: /EMERGENCY STOP/i })
    await expect(emergencyButton).toBeEnabled()

    await emergencyButton.click()
    expect(backend.emergencyCalls).toHaveLength(1)
  })

  test('raises safety lockout when drive command is blocked', async ({ page }) => {
    const backend = new MockBackend()
    backend.setDriveResult({ result: 'blocked', status_reason: 'SAFETY_LOCKOUT' })
    backend.setWebSocketScript([{ message: { event: 'connection.established', client_id: 'control-client' } }])

    await launchApp(page, backend, '/control')

    await page.getByLabel('Confirm Password').fill('admin')
    await page.getByRole('button', { name: 'Unlock Control' }).click()

    await expect(page.getByRole('heading', { name: 'Movement Controls' })).toBeVisible()

    const forwardButton = page.getByRole('button', { name: /Forward/ })
    await forwardButton.dispatchEvent('mousedown')

    const statusAlert = page.locator('.alert').first()
    await expect(statusAlert).toContainText('SAFETY_LOCKOUT')

    const lockoutActive = await page.evaluate(() => {
      return Boolean((window as any).__APP_TEST_HOOKS__?.controlStore?.lockout)
    })
    expect(lockoutActive).toBe(true)
    await expect.poll(() => backend.driveCommands.length).toBe(1)
  })
})

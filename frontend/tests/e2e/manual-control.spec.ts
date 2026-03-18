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
    backend.setDriveResult({
      result: 'blocked',
      status_reason: 'SAFETY_LOCKOUT',
      remediation_link: '/docs/OPERATIONS.md#blade-safety-lockout',
    })
    backend.setWebSocketScript([{ message: { event: 'connection.established', client_id: 'control-client' } }])

    await launchApp(page, backend, '/control')

    await page.getByLabel('Confirm Password').fill('admin')
    await page.getByRole('button', { name: 'Unlock Control' }).click()

    await expect(page.getByRole('heading', { name: 'Movement Controls' })).toBeVisible()

    await page.evaluate(async () => {
      const hooks = (window as any).__APP_TEST_HOOKS__
      await hooks?.controlStore?.submitCommand('drive', {
        session_id: 'e2e-session',
        vector: { linear: 0.4, angular: 0 },
        duration_ms: 120,
        reason: 'e2e-drive',
        max_speed_limit: 0.5,
      })
    })

    await expect.poll(() => backend.driveCommands.length).toBe(1)
    await expect.poll(() => page.evaluate(() => {
      return Boolean((window as any).__APP_TEST_HOOKS__?.controlStore?.lockout)
    })).toBe(true)
    await expect.poll(() => page.evaluate(() => {
      return (window as any).__APP_TEST_HOOKS__?.controlStore?.lockoutDisplay?.label
    })).toBe('Safety lockout')
    await expect.poll(() => page.evaluate(() => {
      return (window as any).__APP_TEST_HOOKS__?.controlStore?.remediationLink
    })).toBe('/docs/OPERATIONS.md#blade-safety-lockout')
  })

  test('shows snapshot fallback when the MJPEG stream cannot be used', async ({ page }) => {
    const backend = new MockBackend()
    backend.setWebSocketScript([{ message: { event: 'connection.established', client_id: 'control-client' } }])

    await launchApp(page, backend, '/control')

    await page.getByLabel('Confirm Password').fill('admin')
    await page.getByRole('button', { name: 'Unlock Control' }).click()

    await expect(page.getByRole('heading', { name: 'Live Camera Feed' })).toBeVisible()
    const cameraFrame = page.locator('.camera-frame').first()
    await expect(cameraFrame).toBeVisible()
    await cameraFrame.dispatchEvent('error')
    await cameraFrame.dispatchEvent('error')

    await expect(page.getByText('SNAPSHOT FALLBACK')).toBeVisible({ timeout: 10000 })
  })
})

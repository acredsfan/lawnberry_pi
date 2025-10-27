import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('System settings persistence', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('persists system settings after saving', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/settings')

    const timezoneSelect = page.getByLabel('Timezone')
    await expect(timezoneSelect).toHaveValue('UTC')

    await timezoneSelect.selectOption('America/New_York')
    await page.getByLabel('Enable Debug Mode').check()
    await page.getByRole('button', { name: 'Save System Settings' }).click()

    const requests = backend.getRequests()
    const saveCall = requests.find((entry) => entry.method === 'PUT' && entry.path === '/api/v2/settings/system')
    expect(saveCall).toBeTruthy()
    expect(saveCall?.body).toMatchObject({ timezone: 'America/New_York', debug_mode: true })

    await page.reload()
    await expect(page.getByLabel('Timezone')).toHaveValue('America/New_York')
    await expect(page.getByLabel('Enable Debug Mode')).toBeChecked()
  })
})

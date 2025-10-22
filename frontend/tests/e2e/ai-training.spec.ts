import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('AI training workflows', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('refreshes dataset summary on load', async ({ page }) => {
    const backend = new MockBackend()
    backend.setTrainingDataset({
      totals: {
        images: 512,
        labeled: 420,
        dataset_bytes: 128 * 1024 * 1024,
        accuracy: 91.4,
      },
    })

    await launchApp(page, backend, '/ai')

    await expect(page.getByRole('heading', { name: 'AI Training' })).toBeVisible()
    await expect(page.locator('.alert-success')).toHaveText(/Dataset refreshed/)

    const datasetRequest = backend
      .getRequests()
      .find((entry) => entry.method === 'GET' && entry.path === '/api/v2/training/dataset')
    expect(datasetRequest).toBeTruthy()
  })

  test('starts a training job with current configuration', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/ai')

    await page.getByRole('button', { name: 'Training', exact: true }).click()

    const startButton = page.getByTestId('ai-start-training')
    await expect(startButton).toHaveText('🚀 Start Training')
    await startButton.click()

    await expect(page.locator('.alert-success')).toHaveText(/Training started successfully/)
    await expect(startButton).toHaveText('🔄 Training...')

    await expect.poll(() => backend.trainingRequests.length).toBe(1)
    expect(backend.trainingRequests[0].payload).toMatchObject({ architecture: 'mobilenet', epochs: 50 })
  })
})

import { test, expect } from '@playwright/test'
import { MockBackend } from './utils/mock-backend'
import { launchApp, resetAppStores } from './utils/test-setup'

test.describe('AI perception console', () => {
  test.beforeEach(async ({ page }) => {
    await resetAppStores(page)
  })

  test('shows live model provenance and fresh detections', async ({ page }) => {
    const backend = new MockBackend()

    await launchApp(page, backend, '/ai')

    await expect(page.getByRole('heading', { name: 'AI Perception' })).toBeVisible()
    await expect(page.getByText('lawnberry-obstacle-detector', { exact: true })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'person' })).toBeVisible()
    await expect(page.getByText('3.0×')).toBeVisible()

    const paths = backend.getRequests().map((entry) => entry.path)
    expect(paths).toContain('/api/v2/ai/status')
    expect(paths).toContain('/api/v2/ai/perception/latest')
    expect(paths).toContain('/api/v2/ai/results/recent')
  })

  test('keeps unavailable runtime explicit and disables inference', async ({ page }) => {
    const backend = new MockBackend()
    backend.setAIStatus({
      model_ready: false,
      active_model_name: null,
      runtime: null,
      model_sha256: null,
      last_error: 'Configured detector manifest not found',
    })
    backend.setPerceptionSnapshot({
      available: false,
      fresh: false,
      reason_code: 'DETECTOR_RUNTIME_UNAVAILABLE',
      result: null,
    })

    await launchApp(page, backend, '/ai')

    await expect(page.getByRole('status')).toContainText('Detector unavailable')
    await expect(page.getByTestId('ai-run-latest')).toBeDisabled()
    await expect(page.getByText('No validated perception result is available.')).toBeVisible()
  })

  test('requests latest-frame inference only from the local owner', async ({ page }) => {
    const backend = new MockBackend()
    await launchApp(page, backend, '/ai')

    await page.getByTestId('ai-run-latest').click()

    await expect.poll(() => backend.inferenceRequests.length).toBe(1)
  })
})

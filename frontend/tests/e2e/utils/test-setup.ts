import type { Page } from '@playwright/test'
import { MockBackend } from './mock-backend'

type LaunchOptions = {
  auth?: boolean
}

export async function launchApp(
  page: Page,
  backend: MockBackend,
  path: string = '/',
  options: LaunchOptions = {},
): Promise<void> {
  await backend.attach(page)

  const url = new URL(path, 'http://localhost')
  if (!url.searchParams.has('e2e')) {
    url.searchParams.set('e2e', '1')
  }

  if (options.auth ?? true) {
  await page.addInitScript(() => {
    const ttl = Date.now() + 60 * 60 * 1000
    try {
      window.localStorage.setItem('auth_token', 'test-token')
      window.localStorage.setItem('token_expiry', ttl.toString())
      window.localStorage.setItem('user_data', JSON.stringify({
        id: 'user-1',
        username: 'admin',
        role: 'admin',
      }))
    } catch (error) {
      console.warn('Failed to seed auth token in init script', error)
    }
  })
  }

  await page.goto(`${url.pathname}${url.search}`)
  await page.waitForLoadState('domcontentloaded')
  try {
    await page.waitForLoadState('networkidle', { timeout: 5000 })
  } catch {
    // Some views keep background polling; proceed once the DOM is ready.
  }
}

export async function resetAppStores(page: Page) {
  await page.evaluate(() => {
    (window as any).__APP_TEST_HOOKS__?.reset?.()
  })
}
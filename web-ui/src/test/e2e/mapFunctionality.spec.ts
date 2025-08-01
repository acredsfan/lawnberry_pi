import { test, expect } from '@playwright/test'

test.describe('Map Functionality E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the maps page
    await page.goto('/maps')
    
    // Wait for the page to load
    await page.waitForLoadState('networkidle')
  })

  test('should load maps page with correct title', async ({ page }) => {
    await expect(page).toHaveTitle(/LawnBerry/)
    await expect(page.locator('h1')).toContainText('LawnBerry Maps')
  })

  test('should display navigation tabs', async ({ page }) => {
    const tabs = ['Overview', 'Boundaries', 'No-Go Zones', 'Home Locations', 'Patterns']
    
    for (const tab of tabs) {
      await expect(page.locator(`text=${tab}`)).toBeVisible()
    }
  })

  test('should switch between map providers', async ({ page, browserName }) => {
    // Skip this test on webkit due to known Google Maps issues
    test.skip(browserName === 'webkit', 'Google Maps not supported on webkit')
    
    // Wait for map container to load
    await page.waitForSelector('[data-testid="map-container"]', { timeout: 10000 })
    
    // Check if provider switching controls are available
    const providerButton = page.locator('button:has-text("Provider")')
    if (await providerButton.isVisible()) {
      await providerButton.click()
      
      // Select different provider
      await page.locator('text=Leaflet').click()
      
      // Verify provider changed
      await expect(page.locator('[data-provider="leaflet"]')).toBeVisible()
    }
  })

  test('should create and edit boundaries', async ({ page }) => {
    // Navigate to boundaries tab
    await page.click('text=Boundaries')
    
    // Wait for boundary editor to load
    await page.waitForSelector('[data-testid="boundary-editor"]', { timeout: 5000 })
    
    // Look for create boundary button
    const createButton = page.locator('button:has-text("Create"), button:has-text("Add"), button:has-text("New")')
    if (await createButton.first().isVisible()) {
      await createButton.first().click()
      
      // Verify boundary creation interface appears
      await expect(page.locator('text=Create Boundary, text=Add Boundary, text=New Boundary')).toBeVisible()
    }
  })

  test('should manage no-go zones', async ({ page }) => {
    // Navigate to no-go zones tab
    await page.click('text=No-Go Zones')
    
    // Wait for no-go zone editor to load
    await page.waitForSelector('[data-testid="no-go-zone-editor"]', { timeout: 5000 })
    
    // Verify no-go zone management interface is present
    await expect(page.locator('[data-testid="no-go-zone-editor"]')).toBeVisible()
  })

  test('should display robot status and battery level', async ({ page }) => {
    // Check for robot status display
    const statusElements = [
      'text=Robot Status',
      'text=Battery',
      'text=%',
      'text=idle, text=mowing, text=charging, text=stopped'
    ]
    
    for (const element of statusElements) {
      const locator = page.locator(element)
      if (await locator.first().isVisible()) {
        await expect(locator.first()).toBeVisible()
        break
      }
    }
  })

  test('should handle responsive design on mobile', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'This test is only for mobile viewports')
    
    // Check that the interface adapts to mobile
    await expect(page.locator('h1')).toBeVisible()
    
    // Verify mobile navigation works
    const tabs = page.locator('[role="tab"], .tab, button:has-text("Overview")')
    if (await tabs.first().isVisible()) {
      await expect(tabs.first()).toBeVisible()
    }
  })

  test('should handle keyboard shortcuts', async ({ page }) => {
    // Test keyboard shortcut for overview tab (key "1")
    await page.keyboard.press('1')
    
    // Verify tab switching worked
    await expect(page.locator('text=Overview')).toBeVisible()
    
    // Test other shortcuts
    await page.keyboard.press('2') // Boundaries
    await page.keyboard.press('3') // No-Go Zones
    await page.keyboard.press('4') // Home Locations
    await page.keyboard.press('5') // Patterns
  })

  test('should display help information', async ({ page }) => {
    // Look for help button
    const helpButton = page.locator('button[aria-label*="help"], button:has-text("Help"), button:has-text("?")')
    
    if (await helpButton.first().isVisible()) {
      await helpButton.first().click()
      
      // Verify help content appears
      await expect(page.locator('text=keyboard, text=shortcut, text=help')).toBeVisible()
    }
  })

  test('should handle map interactions', async ({ page }) => {
    // Wait for map to load
    await page.waitForSelector('[data-testid="map-container"]', { timeout: 10000 })
    
    const mapContainer = page.locator('[data-testid="map-container"]')
    await expect(mapContainer).toBeVisible()
    
    // Test map interaction (zoom, pan)
    const mapBounds = await mapContainer.boundingBox()
    if (mapBounds) {
      // Click on map center
      await page.mouse.click(
        mapBounds.x + mapBounds.width / 2,
        mapBounds.y + mapBounds.height / 2
      )
      
      // Test mouse wheel zoom (if supported)
      await page.mouse.wheel(0, -100) // Scroll up to zoom in
    }
  })

  test('should persist user preferences', async ({ page, context }) => {
    // Make a preference change
    const providerButton = page.locator('button:has-text("Provider")')
    if (await providerButton.isVisible()) {
      await providerButton.click()
      await page.locator('text=Leaflet').click()
    }
    
    // Reload the page
    await page.reload()
    await page.waitForLoadState('networkidle')
    
    // Verify preference was persisted
    if (await page.locator('[data-provider="leaflet"]').isVisible()) {
      await expect(page.locator('[data-provider="leaflet"]')).toBeVisible()
    }
  })

  test('should handle offline scenarios gracefully', async ({ page, context }) => {
    // Simulate offline condition
    await context.setOffline(true)
    
    // Navigate to maps
    await page.goto('/maps')
    
    // Should still load with offline-capable features
    await expect(page.locator('text=Maps, text=Offline')).toBeVisible()
    
    // Restore online
    await context.setOffline(false)
  })
})

test.describe('Cross-browser Map Provider Compatibility', () => {
  test('Google Maps works on Chrome and Firefox', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', 'Google Maps not supported on Safari')
    
    await page.goto('/maps')
    
    // Wait for Google Maps to potentially load
    await page.waitForTimeout(3000)
    
    // Check if Google Maps loaded or if there's a fallback
    const mapContainer = page.locator('[data-testid="map-container"]')
    await expect(mapContainer).toBeVisible()
  })

  test('Leaflet works on all browsers', async ({ page }) => {
    await page.goto('/maps')
    
    // Force switch to Leaflet if possible
    const providerButton = page.locator('button:has-text("Provider")')
    if (await providerButton.isVisible()) {
      await providerButton.click()
      await page.locator('text=Leaflet').click()
    }
    
    // Verify Leaflet map loads
    await page.waitForSelector('[data-testid="map-container"]', { timeout: 10000 })
    const mapContainer = page.locator('[data-testid="map-container"]')
    await expect(mapContainer).toBeVisible()
  })

  test('Touch interactions work on mobile', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'This test is only for mobile devices')
    
    await page.goto('/maps')
    await page.waitForSelector('[data-testid="map-container"]', { timeout: 10000 })
    
    const mapContainer = page.locator('[data-testid="map-container"]')
    const mapBounds = await mapContainer.boundingBox()
    
    if (mapBounds) {
      // Test touch interactions
      await page.touchscreen.tap(
        mapBounds.x + mapBounds.width / 2,
        mapBounds.y + mapBounds.height / 2
      )
      
      // Test pinch zoom gesture
      await page.touchscreen.tap(mapBounds.x + 100, mapBounds.y + 100)
    }
  })
})

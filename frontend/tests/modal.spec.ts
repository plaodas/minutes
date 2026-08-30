import { test, expect } from '@playwright/test'
test.describe('modal focus trap', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', (msg) => console.log('PAGE LOG>', msg.text()))
    page.on('pageerror', (err) => console.log('PAGE ERROR>', err.message))
    // seed localStorage before the app loads so the real UI renders with histories
    await page.addInitScript(() => {
      const now = new Date().toISOString()
      const sample = [{
        id: 'sample-1',
        name: 'rd1487.mp3',
        created_at: now,
        histories: [
          { event_ts: now, event_type: 'status', payload: { result: { output_file: 'outputs/1.txt' } } },
          { event_ts: now, event_type: 'progress', payload: {} },
          { event_ts: now, event_type: 'success', payload: { result: { output_file: 'outputs/2.txt' } } }
        ]
      }]
      try { localStorage.setItem('recent_tasks', JSON.stringify(sample)) } catch (e) {}
    })
    // intercept GET /bg/tasks to return the seeded sample so the UI shows the task
    await page.route('**/bg/tasks**', async (route) => {
      const now = new Date().toISOString()
      const sample = [{ id: 'sample-1', name: 'rd1487.mp3', created_at: now }]
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ tasks: sample }) })
    })
    // intercept GET /bg/tasks/:id/events to return full events including output_file links
    await page.route('**/bg/tasks/sample-1/events', async (route) => {
      const now = new Date().toISOString()
      const resp = {
        task_id: 'sample-1',
        events: [
          { event_ts: now, event_type: 'status', payload: { result: { output_file: 'outputs/1.txt' } } },
          { event_ts: now, event_type: 'progress', payload: {} },
          { event_ts: now, event_type: 'success', payload: { result: { output_file: 'outputs/2.txt' } } }
        ]
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(resp) })
    })
    await page.goto('http://localhost:8080')
    // open the History view via the sidebar so the Recent minutes component is mounted
    await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
    // click the first matching history nav button via DOM to avoid Playwright actionability issues
    await page.evaluate(() => {
      const el = document.querySelector('button[aria-label="History"]') as HTMLElement | null
      el?.click()
    })
    // wait for UI to render (attached to DOM)
    await page.waitForSelector('text=Recent minutes', { state: 'attached', timeout: 10000 })
    // wait for the seeded history button to be attached then scroll into view and click
    await page.waitForSelector('[data-testid="view-history-sample-1"]', { state: 'attached', timeout: 10000 })
    const btn = page.locator('[data-testid="view-history-sample-1"]').first()
    await btn.scrollIntoViewIfNeeded()
    await btn.click()
    await page.waitForSelector('[role="dialog"]')
  })

  test('tabs cycle within modal', async ({ page }) => {
    // close button should be focused first by the app
    const close = page.locator('button[aria-label="Close"]')
    await expect(close).toBeFocused()
    // Tab to first link
    await page.keyboard.press('Tab')
    // After first Tab the Rename button is focused (header button)
    const renameBtn = page.locator('button[data-testid^="rename-"]').first()
    await expect(renameBtn).toBeFocused()
    // Tab to first link
    await page.keyboard.press('Tab')
    const firstLink = page.locator('[role="dialog"] a').first()
    await expect(firstLink).toBeFocused()
    // Tab to second link
    await page.keyboard.press('Tab')
    const secondLink = page.locator('[role="dialog"] a').nth(1)
    await expect(secondLink).toBeFocused()
    // Tab again should wrap back to close
    await page.keyboard.press('Tab')
    await expect(close).toBeFocused()
  })

  test('shift+tab wraps backwards', async ({ page }) => {
    const close = page.locator('button[aria-label="Close"]')
    await expect(close).toBeFocused()
    await page.keyboard.down('Shift')
    await page.keyboard.press('Tab')
    await page.keyboard.up('Shift')
    const lastLink = page.locator('[role="dialog"] a').nth(1)
    await expect(lastLink).toBeFocused()
  })

  test('escape closes modal', async ({ page }) => {
    await page.keyboard.press('Escape')
    await expect(page.locator('[role="dialog"]')).toHaveCount(0)
  })

  test('overlay click closes modal', async ({ page }) => {
    // click outside the dialog by clicking above-left of its bounding box
    const dialog = page.locator('[role="dialog"]')
    const box = await dialog.boundingBox()
    if (box) {
      await page.mouse.click(Math.max(5, box.x - 10), Math.max(5, box.y - 10))
    }
    await expect(page.locator('[role="dialog"]')).toHaveCount(0)
  })
})

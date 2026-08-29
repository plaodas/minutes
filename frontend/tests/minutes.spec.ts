import { test, expect } from '@playwright/test'

test('minutes drawer shows fetched text and actions', async ({ page }) => {
  // mock the minutes endpoint
  await page.route('**/bg/minutes/*', route => {
    route.fulfill({ status: 200, body: 'This is a sample minutes text.\nLine 2\nLine 3' })
  })

  await page.addInitScript(() => {
    const now = new Date().toISOString()
    const sample = [{ id: 'sample-min-1', name: 'upload.mp3', created_at: now, histories: [] }]
    try { localStorage.setItem('recent_tasks', JSON.stringify(sample)) } catch (e) {}
  })

  await page.goto('http://localhost:5173')
  await page.waitForSelector('button[aria-label="History"]')
  await page.evaluate(() => { const el = document.querySelector('button[aria-label="History"]') as HTMLElement | null; el?.click() })
  await page.waitForSelector('[data-testid="view-minutes-sample-min-1"]')
  await page.click('[data-testid="view-minutes-sample-min-1"]')
  // drawer should open and show text
  await page.waitForSelector('role=dialog[name^="Minutes for"]')
  await expect(page.locator('text=This is a sample minutes text.')).toHaveCount(1)
})

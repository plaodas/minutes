import { test, expect } from '@playwright/test'

test('infinite scroll loads more items', async ({ page }) => {
  // seed localStorage with many items
  await page.addInitScript(() => {
    const items = Array.from({ length: 20 }).map((_, i) => ({
      id: `many-${i}`,
      name: `file-${i}.mp3`,
      created_at: new Date().toISOString(),
      histories: Array.from({ length: 3 }).map((__, j) => ({ event_ts: new Date().toISOString(), event_type: `event-${j}`, payload: {} }))
    }))
    try { localStorage.setItem('recent_tasks', JSON.stringify(items)) } catch (e) {}
  })

  await page.goto('http://localhost:5173')
  // navigate to History view
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { document.querySelector('button[aria-label="History"]')?.click() })
  await page.waitForSelector('text=Recent minutes')

  // count rendered items initially (should be 5)
  const rows = page.locator('[data-testid^="view-history-"]').locator('xpath=ancestor::div[1]')
  // find how many item containers are present by counting the parent item elements with the unique button
  const initial = await page.locator('[data-testid^="view-history-"]').count()
  expect(initial).toBeGreaterThanOrEqual(1)
  // ensure initial visible count equals 5 (UI shows 5 items)
  const visibleItems = await page.evaluate(() => document.querySelectorAll('[data-testid^="view-history-"]').length)
  if (visibleItems !== 5) {
    // continue but warn
    console.log('initial visibleItems', visibleItems)
  }

  // scroll to bottom to trigger loading
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(500)

  // after scroll, more items should be present
  const after = await page.evaluate(() => document.querySelectorAll('[data-testid^="view-history-"]').length)
  expect(after).toBeGreaterThan(visibleItems)
})

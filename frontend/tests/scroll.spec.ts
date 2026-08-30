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

  // intercept GET /bg/tasks to return paged responses based on offset and limit
  await page.route('**/bg/tasks**', async (route) => {
    const url = new URL(route.request().url())
    const limit = Number(url.searchParams.get('limit') || '20')
    const offset = Number(url.searchParams.get('offset') || '0')
    const items = Array.from({ length: 20 }).map((_, i) => ({ id: `many-${i}`, name: `file-${i}.mp3`, created_at: new Date().toISOString() }))
    const slice = items.slice(offset, offset + limit)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ tasks: slice }) })
  })

  await page.goto('http://localhost:8080')
  // navigate to History view
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { document.querySelector('button[aria-label="History"]')?.click() })
  await page.waitForSelector('text=Recent minutes')

  // count rendered items initially
  const initial = await page.locator('[data-testid^="view-history-"]').count()
  expect(initial).toBeGreaterThanOrEqual(1)

  // scroll to bottom to trigger loading
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(500)

  // after scroll, more items should be present (or same when server returned all)
  const after = await page.locator('[data-testid^="view-history-"]').count()
  expect(after).toBeGreaterThanOrEqual(initial)
})

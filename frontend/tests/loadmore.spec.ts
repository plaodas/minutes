import { test, expect } from '@playwright/test'

test('modal load more appends histories', async ({ page }) => {
  // seed localStorage with one item that already has 2 history entries
  await page.addInitScript(() => {
    const now = new Date().toISOString()
    const sample = [{ id: 'loadmore-1', name: 'LoadMore Test', created_at: now, histories: [
      { event_ts: now, event_type: 'START', payload: {} },
      { event_ts: now, event_type: 'PROCESS', payload: {} },
    ] }]
    try { localStorage.setItem('recent_tasks', JSON.stringify(sample)) } catch (e) {}
  })

  // intercept GET /bg/tasks to return the seeded task list (paged)
  await page.route('**/bg/tasks**', async (route) => {
    const url = new URL(route.request().url())
    const limit = Number(url.searchParams.get('limit') || '20')
    const offset = Number(url.searchParams.get('offset') || '0')
    const now = new Date().toISOString()
    const all = [{ id: 'loadmore-1', name: 'LoadMore Test', created_at: now }]
    const slice = all.slice(offset, offset + limit)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ tasks: slice }) })
  })

  // intercept GET /bg/tasks/:id/events to return full events including MORE
  await page.route('**/bg/tasks/loadmore-1/events', async (route) => {
    const now = new Date().toISOString()
    const resp = { task_id: 'loadmore-1', events: [
      { event_ts: now, event_type: 'START', payload: {} },
      { event_ts: now, event_type: 'PROCESS', payload: {} },
      { event_ts: now, event_type: 'MORE', payload: { info: 'more1' } },
    ] }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(resp) })
  })

  await page.goto('http://localhost:5173')
  // navigate to History view via the sidebar
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { document.querySelector('button[aria-label="History"]')?.click() })
  await page.waitForSelector('text=Recent minutes')
  const hasHistoryBtn = await page.evaluate(() => !!document.querySelector('button[aria-label="History"]'))
  console.log('HAS_HISTORY_BTN', hasHistoryBtn)
  const labels = await page.evaluate(() => Array.from(document.querySelectorAll('button[aria-label]')).map((b) => (b as HTMLElement).getAttribute('aria-label')))
  console.log('ARIA_LABELS', labels)
  // debug: log how many view-history buttons are present and body content
  const count = await page.evaluate(() => document.querySelectorAll('[data-testid^="view-history-"]').length)
  const body = await page.evaluate(() => document.body.innerHTML)
  console.log('VIEW_HISTORY_COUNT', count)
  console.log('BODY_HTML', body.slice(0, 2000))
  const stored = await page.evaluate(() => localStorage.getItem('recent_tasks'))
  console.log('STORED_RECENT_TASKS', stored)
  const bodyText = await page.evaluate(() => document.body.innerText)
  console.log('BODY_TEXT', bodyText.slice(0, 2000))
  // open the history modal via the real button
  await page.click('[data-testid="view-history-loadmore-1"]')
  await page.waitForSelector('[role="dialog"]')
  const dialog = page.locator('[role="dialog"]')
  await expect(dialog.getByText(/Full history for/)).toBeVisible()

  // debug: log dialog HTML to inspect Load more button
  const html = await page.evaluate(() => document.querySelector('[role="dialog"]')?.innerHTML)
  console.log('DIALOG_HTML', (html || '').slice(0, 2000))

  // confirm initial entries exist within the dialog
  await expect(dialog.getByText('START')).toBeVisible()
  await expect(dialog.getByText('PROCESS')).toBeVisible()

  // click Load more and expect the MORE entry to appear, or if server indicated none, accept 'No more history'
  // the modal now fetches all events in one request; assert the MORE event is present
  await expect(dialog.getByText('MORE', { exact: true })).toBeVisible()
})

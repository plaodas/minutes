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

  // intercept POST /bg/histories to return one more event when offset === 2
  await page.route('**/bg/histories', async (route) => {
    const req = route.request()
    let post: any = {}
    try { post = req.postDataJSON() } catch (e) { post = {} }
    const ids = post.ids || []
    const offset = post.offset || 0
    const resp: any = { histories: {} }
    if (ids.includes('loadmore-1') && offset === 2) {
      resp.histories['loadmore-1'] = [
        { event_ts: new Date().toISOString(), event_type: 'MORE', payload: { info: 'more1' } },
      ]
    } else {
      resp.histories['loadmore-1'] = []
    }
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
  await expect(dialog.getByText('Full history for loadmore-1')).toBeVisible()

  // confirm initial entries exist within the dialog
  await expect(dialog.getByText('START')).toBeVisible()
  await expect(dialog.getByText('PROCESS')).toBeVisible()

  // click Load more and expect the MORE entry to appear
  await dialog.getByTestId(`load-more-loadmore-1`).click()
  await expect(dialog.getByText('MORE', { exact: true })).toBeVisible()
})

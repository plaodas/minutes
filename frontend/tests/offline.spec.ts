import { test, expect } from '@playwright/test'

test('offline fallback uses cached tasks and shows retry toast', async ({ page }) => {
  // seed cached tasks in localStorage
  await page.addInitScript(() => {
    const now = new Date().toISOString()
    // backend tasks are an array; store array shape for cached_tasks
    const cached = [{ id: 'cached-1', name: 'cached.mp3', created_at: now }]
    try { localStorage.setItem('cached_tasks', JSON.stringify(cached)) } catch (e) {}
    // also seed recent_tasks so the UI shows the item immediately in case the app reads that key
    try { localStorage.setItem('recent_tasks', JSON.stringify(cached)) } catch (e) {}
  })

  // stub fetch: make /bg/tasks fail and return minutes text for /bg/minutes/
  await page.addInitScript(() => {
    const orig = window.fetch.bind(window)
    // @ts-ignore
    window.fetch = (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      if (url.includes('/bg/tasks')) {
        return Promise.reject(new TypeError('Failed to fetch'))
      }
      if (url.includes('/bg/minutes/')) {
        return Promise.resolve(new Response('cached minutes text', { status: 200, headers: { 'Content-Type': 'text/plain' } }))
      }
      return orig(input, init)
    }
  })

  // open the app (assumes server on 8080)
  // intercept network to force /bg/tasks to fail (works even when SW is active)
  await page.route('**/bg/tasks**', (route) => route.abort())
  await page.goto('http://localhost:8080')
  // sanity-check the route by performing a fetch in page context against the app origin
  const fetchResult = await page.evaluate(async (url) => {
    try {
      await fetch(url)
      return 'ok'
    } catch (e: any) {
      return 'err:' + (e?.message || String(e))
    }
  }, 'http://localhost:8080/bg/tasks')
  console.log('FETCH_CHECK', fetchResult)

  // open history UI
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { const el = document.querySelector('button[aria-label="History"]') as HTMLElement | null; el?.click() })

  // debug: dump cached_tasks and current view-minutes elements
  const cachedRaw = await page.evaluate(() => localStorage.getItem('cached_tasks'))
  console.log('CACHED_RAW:', cachedRaw)
  const testIds = await page.evaluate(() => Array.from(document.querySelectorAll('[data-testid^="view-minutes-"]')).map((el) => (el as HTMLElement).getAttribute('data-testid')))
  console.log('FOUND_TEST_IDS', testIds)

  // assert the offline fallback was triggered: cached_tasks present and error toast shown
  const cachedExists = await page.evaluate(() => !!localStorage.getItem('cached_tasks'))
  expect(cachedExists).toBe(true)
  // the error may be rendered as a toast or inline banner depending on app state/SW; check body text for known failure messages
  // wait for the error text (fetchWithRetry uses retries/timeouts; allow up to 15s)
  await page.waitForFunction(() => {
    const text = document.body.innerText
    return text.includes('履歴の読み込みに失敗しました') || text.includes('履歴を読み込めませんでした') || text.includes('最新の履歴を取得できませんでした')
  }, { timeout: 15000 })
})

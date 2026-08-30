import { test, expect } from '@playwright/test'

test('offline fallback uses cached tasks and shows retry toast', async ({ page }) => {
  // seed cached tasks in localStorage
  await page.addInitScript(() => {
    const now = new Date().toISOString()
    // backend tasks are an array; store array shape for cached_tasks
    const cached = [{ id: 'cached-1', name: 'cached.mp3', created_at: now }]
    try { localStorage.setItem('cached_tasks', JSON.stringify(cached)) } catch (e) {}
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
  await page.goto('http://localhost:8080')

  // open history UI
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { const el = document.querySelector('button[aria-label="History"]') as HTMLElement | null; el?.click() })

  // debug: dump cached_tasks and current view-minutes elements
  const cachedRaw = await page.evaluate(() => localStorage.getItem('cached_tasks'))
  console.log('CACHED_RAW:', cachedRaw)
  const testIds = await page.evaluate(() => Array.from(document.querySelectorAll('[data-testid^="view-minutes-"]')).map((el) => (el as HTMLElement).getAttribute('data-testid')))
  console.log('FOUND_TEST_IDS', testIds)

  // cached task should be visible (use data-testid to avoid text-matching edge cases)
  await page.waitForSelector('[data-testid="view-minutes-cached-1"]', { timeout: 5000 })
  const item = page.locator('[data-testid="view-minutes-cached-1"]')
  await expect(item.getByText('cached.mp3')).toBeVisible()

  // toast for failure should appear with retry action
  await page.waitForSelector('text=履歴の読み込みに失敗しました', { timeout: 5000 })
  await expect(page.locator('text=再試行')).toBeVisible()
})

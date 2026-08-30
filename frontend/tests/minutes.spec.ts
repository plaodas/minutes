import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

test('minutes drawer shows fetched text and actions', async ({ page }) => {
  // mock the minutes endpoint
  await page.addInitScript(() => {
    const now = new Date().toISOString()
    const sample = [{ id: 'sample-min-1', name: 'upload.mp3', created_at: now, histories: [] }]
    try { localStorage.setItem('recent_tasks', JSON.stringify(sample)) } catch (e) {}
  })

  // intercept GET /bg/tasks so the UI renders the seeded task
  await page.addInitScript(() => {
    const orig = window.fetch.bind(window)
    // @ts-ignore
    window.fetch = (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      if (url.includes('/bg/tasks')) {
        const now = new Date().toISOString()
        const sample = [{ id: 'sample-min-1', name: 'upload.mp3', created_at: now }]
        return Promise.resolve(new Response(JSON.stringify({ tasks: sample }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      }
      return orig(input, init)
    }
  })

  // stub fetch for minutes endpoint in-page to avoid cross-origin/network issues
  await page.addInitScript(() => {
    const orig = window.fetch.bind(window)
    // @ts-ignore
    window.fetch = (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      if (url.includes('/bg/minutes/')) {
        return Promise.resolve(new Response('This is a sample minutes text.\nLine 2\nLine 3', { status: 200, headers: { 'Content-Type': 'text/plain' } }))
      }
      return orig(input, init)
    }
  })

  await page.goto('http://localhost:8080')
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { const el = document.querySelector('button[aria-label="History"]') as HTMLElement | null; el?.click() })
  await page.waitForSelector('button[aria-label^="View minutes for"]', { state: 'attached', timeout: 10000 })
  await page.click('button[aria-label^="View minutes for"]')
  // drawer should open and show text (wait for route to be invoked and dialog to render)
  await page.waitForSelector('role=dialog[name^="Minutes for"]')
  await page.waitForSelector('button:has-text("Download")', { timeout: 10000 })
  await expect(page.locator('text=This is a sample minutes text.').first()).toBeVisible()
})

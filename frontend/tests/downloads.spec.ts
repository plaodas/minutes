import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

test('download buttons call backend endpoints', async ({ page }) => {
  // seed recent tasks so history shows an item
  await page.addInitScript(() => {
    const now = new Date().toISOString()
    const sample = [{ id: 'sample-min-2', name: 'upload.mp3', created_at: now, histories: [] }]
    try { localStorage.setItem('recent_tasks', JSON.stringify(sample)) } catch (e) {}
  })

  // stub /bg/tasks and /bg/minutes via in-page fetch override so the UI shows our seeded task reliably
  await page.addInitScript(() => {
    const orig = window.fetch.bind(window)
    // @ts-ignore
    window.fetch = (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      if (url.includes('/bg/tasks')) {
        const now = new Date().toISOString()
        const sample = [{ id: 'sample-min-2', name: 'upload.mp3', created_at: now }]
        return Promise.resolve(new Response(JSON.stringify({ tasks: sample }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      }
      if (url.includes('/bg/minutes/')) {
        return Promise.resolve(new Response('Sample minutes for download test', { status: 200, headers: { 'Content-Type': 'text/plain' } }))
      }
      return orig(input, init)
    }
  })

  // in-page fetch stub for download endpoints and counters (works with service worker too)
  await page.addInitScript(() => {
    // counters
    // @ts-ignore
    window.__transcriptCalled = 0
    // @ts-ignore
    window.__summaryCalled = 0
    // @ts-ignore
    window.__actionsCalled = 0
    const orig = window.fetch.bind(window)
    // @ts-ignore
    window.fetch = (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      if (url.includes('/api/bg/transcript/')) {
        // @ts-ignore
        window.__transcriptCalled++
        return Promise.resolve(new Response('TRANSCRIPT', { status: 200, headers: { 'Content-Type': 'text/plain' } }))
      }
      if (url.includes('/api/bg/summary/')) {
        // @ts-ignore
        window.__summaryCalled++
        return Promise.resolve(new Response('SUMMARY', { status: 200, headers: { 'Content-Type': 'text/plain' } }))
      }
      if (url.includes('/api/bg/action-items/')) {
        // @ts-ignore
        window.__actionsCalled++
        return Promise.resolve(new Response(JSON.stringify({ items: [{ text: 'Do thing' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      }
      return orig(input, init)
    }
  })

  await page.goto('http://localhost:8080')
  await page.waitForSelector('button[aria-label="History"]', { state: 'attached', timeout: 10000 })
  await page.evaluate(() => { const el = document.querySelector('button[aria-label="History"]') as HTMLElement | null; el?.click() })
  await page.waitForSelector('button[aria-label^="View minutes for"]', { state: 'attached', timeout: 10000 })
  // click the chevron to open the MinutesDrawer (stable selector)
  await page.click('button[aria-label^="View minutes for"]')
  await page.waitForSelector('role=dialog[name^="Minutes for"]')

  // click the Download buttons in the drawer; ensure they are scrolled into view first
  const transcriptBtn = page.locator('button:has-text("Download transcript")')
  await transcriptBtn.scrollIntoViewIfNeeded()
  await transcriptBtn.click()

  const summaryBtn = page.locator('button:has-text("Download summary")')
  await summaryBtn.scrollIntoViewIfNeeded()
  await summaryBtn.click()

  const actionsBtn = page.locator('button:has-text("Download action items")')
  await actionsBtn.scrollIntoViewIfNeeded()
  await actionsBtn.click()

  // allow in-page handlers to be hit
  await page.waitForTimeout(200)
  const counts = await page.evaluate(() => ({ t: (window as any).__transcriptCalled || 0, s: (window as any).__summaryCalled || 0, a: (window as any).__actionsCalled || 0 }))
  expect(counts.t).toBeGreaterThanOrEqual(1)
  expect(counts.s).toBeGreaterThanOrEqual(1)
  expect(counts.a).toBeGreaterThanOrEqual(1)
})

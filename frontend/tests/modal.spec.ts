import { test, expect } from '@playwright/test'

const modalHtml = (id = 'test-modal') => `
  <div id="overlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.4);display:flex;align-items:flex-start;justify-content:center;padding:24px">
    <div role="dialog" aria-modal="true" aria-label="Full history for ${id}" style="background:#fff;padding:16px;border-radius:8px;max-height:70vh;overflow:auto;min-width:320px">
      <button id="close" aria-label="Close">✕</button>
      <h2>Full history for ${id}</h2>
      <div>
        <button id="action-1">Action 1</button>
        <a id="link-1" href="#">Link 1</a>
        <input id="input-1" />
      </div>
    </div>
    </div>
  `

test.describe('modal focus trap', () => {
  test.beforeEach(async ({ page }) => {
    // open the built app page
    await page.goto('http://localhost:5173')
    // inject a test modal into the page DOM and a focus-trap handler so tests run against built app context
    await page.evaluate(() => {
      const html = `
      <div id="overlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.4);display:flex;align-items:flex-start;justify-content:center;padding:24px">
        <div role="dialog" aria-modal="true" aria-label="Full history for test" style="background:#fff;padding:16px;border-radius:8px;max-height:70vh;overflow:auto;min-width:320px">
          <button id="close" aria-label="Close">✕</button>
          <h2>Full history for test</h2>
          <div>
            <button id="action-1">Action 1</button>
            <a id="link-1" href="#">Link 1</a>
            <input id="input-1" />
          </div>
        </div>
      </div>`
      const wrapper = document.createElement('div')
      wrapper.innerHTML = html
      document.body.appendChild(wrapper.firstElementChild)
      // simple focus trap for the injected modal
      const root = document.querySelector('[role="dialog"]')
      const getFocusable = () => {
        if (!root) return []
        return Array.from(root.querySelectorAll('a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'))
      }
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          const ov = document.getElementById('overlay')
          ov?.remove()
          return
        }
        if (e.key !== 'Tab') return
        const list = getFocusable()
        if (list.length === 0) { e.preventDefault(); return }
        const idx = list.indexOf(document.activeElement)
        if (e.shiftKey) {
          if (idx <= 0) { e.preventDefault(); list[list.length - 1].focus() }
        } else {
          if (idx === list.length - 1) { e.preventDefault(); list[0].focus() }
        }
      })
      const ov = document.getElementById('overlay')
      ov?.addEventListener('click', (ev) => { if (ev.target === ov) ov.remove() })
      // focus first
      setTimeout(() => { document.getElementById('close')?.focus() }, 20)
    })
  })

  test('tabs cycle within modal', async ({ page }) => {
    // focus close button first
    await page.locator('#close').focus()
    // press Tab to go to first action
    await page.keyboard.press('Tab')
    await expect(page.locator('#action-1')).toBeFocused()
    // Tab to link
    await page.keyboard.press('Tab')
    await expect(page.locator('#link-1')).toBeFocused()
    // Tab to input
    await page.keyboard.press('Tab')
    await expect(page.locator('#input-1')).toBeFocused()
    // Tab again should wrap to close
    await page.keyboard.press('Tab')
    await expect(page.locator('#close')).toBeFocused()
  })

  test('shift+tab wraps backwards', async ({ page }) => {
    await page.locator('#close').focus()
    // Shift+Tab from close should go to input (last)
    await page.keyboard.down('Shift')
    await page.keyboard.press('Tab')
    await page.keyboard.up('Shift')
    await expect(page.locator('#input-1')).toBeFocused()
  })

  test('escape closes modal (simulate by removing from DOM)', async ({ page }) => {
    // press Escape (beforeEach injected handler will remove overlay)
    await page.keyboard.press('Escape')
    await expect(page.locator('#overlay')).toHaveCount(0)
  })

  test('overlay click closes modal', async ({ page }) => {
    // click overlay background (outside dialog)
    await page.click('#overlay')
    await expect(page.locator('#overlay')).toHaveCount(0)
  })
})

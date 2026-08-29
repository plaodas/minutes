import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  webServer: {
    command: 'node ./scripts/serve-dist.js',
    port: 5173,
    reuseExistingServer: false,
    timeout: 30_000,
  },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})

import { defineConfig, devices } from '@playwright/test'

const E2E_PORT = process.env.E2E_PORT || process.env.PORT || '8080'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  webServer: {
    command: `PORT=${E2E_PORT} node ./scripts/serve-dist.js`,
    port: Number(E2E_PORT),
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

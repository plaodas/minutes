import { test, expect } from '@playwright/test'

test('live status advances processing steps and closes transcription progress', async ({ page }) => {
  const taskId = 'dd3a1d68-07f0-413a-b337-9f39c2d3ce76'

  await page.addInitScript(() => {
    const instances: Array<{ onmessage: ((event: MessageEvent) => void) | null }> = []

    class MockEventSource {
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null

      constructor() {
        instances.push(this)
      }

      close() {}
    }

    Object.defineProperty(window, 'EventSource', { value: MockEventSource })
    ;(window as any).__emitTaskEvent = (event: unknown) => {
      for (const instance of instances) {
        instance.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
  })

  await page.route('**/api/transcribe-upload-bg', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ task_id: taskId }),
    })
  })
  await page.route(`**/api/bg/status/${taskId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ task_id: taskId, status: 'transcribing' }),
    })
  })

  await page.goto(process.env.E2E_PORT ? `http://localhost:${process.env.E2E_PORT}` : 'http://localhost:8080')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'meeting.mp3',
    mimeType: 'audio/mpeg',
    buffer: Buffer.from('test audio'),
  })
  await expect(page.getByText(`Task: ${taskId}`)).toBeVisible()

  const emit = (eventType: string, payload: Record<string, unknown>) => page.evaluate(
    ({ taskId, eventType, payload }) => {
      ;(window as any).__emitTaskEvent({
        type: 'task.event',
        task_id: taskId,
        event_type: eventType,
        payload,
      })
    },
    { taskId, eventType, payload },
  )

  await emit('status', { status: 'transcribing' })
  await emit('progress', { progress: 100 })
  await expect(page.getByText('Transcribing: 100%')).toBeVisible()
  await expect(page.locator('section[aria-label="Processing status"] > div > span')).toHaveText('Step 3 of 4')

  await emit('status', { status: 'formatting' })
  await expect(page.locator('section[aria-label="Processing status"] > div > span')).toHaveText('Step 4 of 4')
  await expect(page.getByText('Transcribing: 100%')).toHaveCount(0)

  await emit('failure', { error: 'transcription failed' })
  await expect(page.getByText('Error: transcription failed')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel' })).toHaveCount(0)
})

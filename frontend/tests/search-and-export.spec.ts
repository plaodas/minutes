import { expect, test } from '@playwright/test';

const task = {
  id: 'task-1',
  name: '予算会議',
  status: 'success',
  created_at: '2026-10-03T00:00:00',
  result: {
    segments: [
      { start: 0, end: 2, text: 'こんにちは' },
      { start: 2, end: 4, text: '了解しました' },
    ],
    transcript: 'こんにちは\n了解しました',
    summary: '挨拶',
    minutes: '会議の本文',
  },
};

async function authenticate(page: import('@playwright/test').Page) {
  await page.route('**/api/auth/features', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        user: { email: 'owner@example.com' },
        features: { registration_enabled: false },
      }),
    });
  });
}

test('history search resets to the first page after debounce', async ({ page }) => {
  const requests: string[] = [];
  await authenticate(page);
  await page.route('**/api/bg/tasks**', async (route) => {
    requests.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ tasks: [], count: 0 }),
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'History' }).click();
  await page.getByLabel('Search minutes').fill('予算会議');
  await expect.poll(() => requests.some((url) => url.includes('q='))).toBeTruthy();
  const searched = requests.filter((url) => url.includes('q='));
  expect(searched.at(-1)).toContain('offset=0');
  expect(searched.at(-1)).toContain(encodeURIComponent('予算会議'));
});

test('assigns one speaker to selected segments and downloads docx', async ({ page }) => {
  const speakerBodies: string[] = [];
  const downloads: string[] = [];
  await authenticate(page);
  await page.route('**/api/bg/tasks**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ tasks: [task], count: 1 }),
    });
  });
  await page.route('**/api/bg/result/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', result: task.result }),
    });
  });
  await page.route('**/api/bg/minutes/**', async (route) => {
    const url = route.request().url();
    downloads.push(url);
    if (url.includes('format=docx')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        body: Buffer.from('docx'),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'text/plain', body: '会議の本文' });
  });
  await page.route('**/api/bg/summary/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/plain', body: '挨拶' });
  });
  await page.route('**/api/bg/task/**/speakers', async (route) => {
    speakerBodies.push(route.request().postData() || '');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: 'task-1',
        transcript: '[山田] こんにちは\n[山田] 了解しました',
        segments: [
          { start: 0, end: 2, text: 'こんにちは', speaker: '山田' },
          { start: 2, end: 4, text: '了解しました', speaker: '山田' },
        ],
      }),
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'History' }).click();
  await page.getByTestId('view-minutes-task-1').click();
  await page.getByLabel('Select segment 1').check();
  await page.getByLabel('Select segment 2').check();
  await page.getByLabel('Speaker name').fill('山田');
  await page.getByRole('button', { name: 'Apply to selection' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect.poll(() => speakerBodies.length).toBe(1);
  expect(JSON.parse(speakerBodies[0])).toEqual({
    updates: [
      { index: 0, speaker: '山田' },
      { index: 1, speaker: '山田' },
    ],
  });
  await page.getByRole('button', { name: 'Word minutes' }).click();
  await expect.poll(() => downloads.some((url) => url.includes('format=docx'))).toBeTruthy();
});

test('history full text renders markdown headings and speaker names', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/bg/tasks**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ tasks: [task], count: 1 }),
    });
  });
  await page.route('**/api/bg/result/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', result: task.result }),
    });
  });
  await page.route('**/api/bg/summary/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/plain', body: '会議の要点' });
  });
  await page.route('**/api/bg/minutes/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/plain',
      body: '### 整形済み議事録\n\n**A** 本日はありがとうございます。',
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'History' }).click();
  await page.getByTestId('view-minutes-task-1').click();
  await expect(page.getByText('会議の要点')).toBeVisible();
  await expect(page.getByRole('heading', { name: '整形済み議事録' })).toBeVisible();
  await expect(page.getByText('A', { exact: true })).toBeVisible();
  await expect(page.getByText('### 整形済み議事録')).toHaveCount(0);
  await expect(page.getByText('**A**')).toHaveCount(0);
});

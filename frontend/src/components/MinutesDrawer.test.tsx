import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MinutesDrawer } from './MinutesDrawer';
import { ToastProvider } from './ToastProvider';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function textResponse(body: string, status = 200) {
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'text/plain' },
  });
}

function mockFetch(minutes: Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/bg/tasks')) return jsonResponse({ tasks: [] });
      if (url.includes('/bg/result/')) {
        return jsonResponse({
          status: 'success',
          result: {
            segments: [{ start: 1.52, end: 3.52, text: 'メン、ミカン' }],
          },
        });
      }
      if (url.includes('/bg/summary/')) return textResponse('短い要約');
      if (url.includes('/bg/transcript/')) return textResponse('メン、ミカン');
      if (url.includes('/bg/minutes/')) return minutes;
      return jsonResponse({ error: 'unknown' }, 404);
    })
  );
}

function renderDrawer() {
  return render(
    <ToastProvider>
      <MinutesDrawer taskId="task-1" onClose={() => undefined} />
    </ToastProvider>
  );
}

describe('MinutesDrawer', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows the summary and minutes downloads when a minutes file exists', async () => {
    mockFetch(textResponse('整形済みの議事録です'));

    renderDrawer();

    expect(await screen.findByText('要約')).toBeTruthy();
    expect((await screen.findAllByText('整形済みの議事録です')).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Word 議事録' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '要約をダウンロード' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'アクションアイテムをダウンロード' })).toBeTruthy();
    expect(screen.getByText('話者')).toBeTruthy();
  });

  it('shows the transcript when minutes were not created', async () => {
    mockFetch(jsonResponse({ error: 'no output file available' }, 404));

    renderDrawer();

    expect((await screen.findAllByText('メン、ミカン')).length).toBeGreaterThan(0);
    expect(screen.queryByText('要約')).toBeNull();
    expect(screen.queryByText('取得に失敗しました')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Word 議事録' })).toBeNull();
    expect(screen.queryByRole('button', { name: '要約をダウンロード' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'アクションアイテムをダウンロード' })).toBeNull();
    expect(screen.getByRole('button', { name: '文字起こしをダウンロード' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'コピー' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'リンクをコピー' })).toBeTruthy();
    expect(screen.getByText('話者')).toBeTruthy();
    expect(screen.getByText('全文')).toBeTruthy();
  });

  it('keeps other minutes failures as errors', async () => {
    mockFetch(jsonResponse({ error: 'unknown task' }, 404));

    renderDrawer();

    expect(await screen.findByText('取得に失敗しました')).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText('メン、ミカン')).toBeNull();
    });
    expect(screen.queryByRole('button', { name: '文字起こしをダウンロード' })).toBeNull();
  });
});

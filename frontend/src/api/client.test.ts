import { afterEach, describe, expect, it, vi } from 'vitest';

import { cancelTask, fetchMinutesDocx, updateTaskSpeakers } from './client';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('cancelTask', () => {
  it('requests cancellation for the active backend task', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ task_id: 'task/1', cancelled: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(cancelTask('task/1')).resolves.toEqual({
      task_id: 'task/1',
      cancelled: true,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/bg/cancel/task%2F1',
      expect.objectContaining({ method: 'POST' })
    );
  });
});

describe('speaker and docx client', () => {
  it('posts selected speaker updates', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ transcript: '[山田] こんにちは', segments: [{ speaker: '山田' }] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      );
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      updateTaskSpeakers('task-1', [
        { index: 0, speaker: '山田' },
        { index: 1, speaker: '山田' },
      ])
    ).resolves.toMatchObject({ transcript: '[山田] こんにちは' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/bg/task/task-1/speakers',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('downloads a docx minutes file', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(['docx']), {
        status: 200,
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        },
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    const downloaded = await fetchMinutesDocx('task-1');
    expect(downloaded.blob.size).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith('/api/bg/minutes/task-1?format=docx', expect.anything());
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';

import { cancelTask } from './client';

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

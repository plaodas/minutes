import React from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, it, vi, beforeEach, expect } from 'vitest';

import { ToastProvider } from '../components/ToastProvider';
import { TaskEventsProvider } from '../events/TaskEventsProvider';

import { useTasks } from './useTasks';

// Test component to expose hook state
function TestComponent() {
  const { tasks, loading, error } = useTasks();
  return (
    <div>
      <div data-testid="loading">{loading ? '1' : '0'}</div>
      <div data-testid="error">{error ? '1' : '0'}</div>
      <div data-testid="tasks">{tasks ? JSON.stringify(tasks) : ''}</div>
    </div>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  // clear localStorage
  try {
    localStorage.clear();
  } catch (e) {}
});

afterEach(() => cleanup());

describe('useTasks', () => {
  it('loads tasks and caches them', async () => {
    const mockData = { tasks: [{ id: 't1' }, { id: 't2' }] };
    // mock fetchWithRetry module
    const mod = await import('../lib/fetchWithRetry');
    vi.spyOn(mod, 'default').mockResolvedValue(
      new Response(JSON.stringify(mockData), { status: 200 })
    );

    render(
      <TaskEventsProvider>
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      </TaskEventsProvider>
    );

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('0'));
    expect(screen.getByTestId('tasks').textContent).toContain('t1');
    // cached
    expect(localStorage.getItem('cached_tasks')).toBeTruthy();
  });

  it('falls back to cache on network failure and shows toast', async () => {
    const cached = { tasks: [{ id: 'cached1' }] };
    localStorage.setItem('cached_tasks', JSON.stringify(cached));
    const mod = await import('../lib/fetchWithRetry');
    vi.spyOn(mod, 'default').mockRejectedValue(new Error('network'));

    render(
      <TaskEventsProvider>
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      </TaskEventsProvider>
    );

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('0'));
    expect(screen.getByTestId('tasks').textContent).toContain('cached1');
  });

  it('polls only while the task event connection is unavailable', async () => {
    const instances: MockEventSource[] = [];

    class MockEventSource {
      onmessage: ((event: MessageEvent) => void) | null = null;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn();

      constructor() {
        instances.push(this);
      }
    }

    vi.stubGlobal('EventSource', MockEventSource);
    const mod = await import('../lib/fetchWithRetry');
    const fetchSpy = vi.spyOn(mod, 'default').mockImplementation(async () => {
      return new Response(JSON.stringify({ tasks: [{ id: 't1' }] }), { status: 200 });
    });

    const view = render(
      <TaskEventsProvider>
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      </TaskEventsProvider>
    );

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    act(() => instances[0].onopen?.());
    vi.useFakeTimers();
    try {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      act(() => instances[0].onerror?.());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      act(() => instances.at(-1)?.onopen?.());
      await act(async () => {
        await Promise.resolve();
      });
      expect(fetchSpy).toHaveBeenCalledTimes(3);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(3);
    } finally {
      view.unmount();
      vi.useRealTimers();
      vi.unstubAllGlobals();
    }
  });
});

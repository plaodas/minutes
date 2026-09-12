import React from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TaskEventsProvider } from '../events/TaskEventsProvider';

import { useActiveTask } from './useActiveTask';

type HookState = ReturnType<typeof useActiveTask>;

function TestComponent({
  taskId,
  onReady,
}: {
  taskId: string | null;
  onReady: (state: HookState) => void;
}) {
  const state = useActiveTask(taskId, {});
  onReady(state);
  return <div data-testid="stage">{state.task?.stage || ''}</div>;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

describe('useActiveTask', () => {
  it('applies shared task events to the active upload task', async () => {
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
    const onStageIndex = vi.fn();
    const onResult = vi.fn();
    let latest: HookState | null = null;

    function Consumer() {
      latest = useActiveTask('task-1', { onStageIndex, onResult });
      return <div data-testid="stage">{latest.task?.stage || ''}</div>;
    }

    const view = render(
      <TaskEventsProvider>
        <Consumer />
      </TaskEventsProvider>
    );

    await waitFor(() => expect(instances).toHaveLength(1));
    act(() => instances[0].onopen?.());
    act(() => {
      instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'task.event',
          task_id: 'task-1',
          event_type: 'status',
          stage: 'transcribing',
          payload: { status: 'transcribing' },
        }),
      } as MessageEvent);
    });

    expect(latest?.task).toMatchObject({ status: 'transcribing', stage: 'transcribing' });
    expect(onStageIndex).toHaveBeenCalledWith(2);

    act(() => {
      instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'task.event',
          task_id: 'task-1',
          event_type: 'success',
          stage: 'success',
          payload: { result: { summary: 'done' } },
        }),
      } as MessageEvent);
    });

    await waitFor(() =>
      expect(onResult).toHaveBeenCalledWith({ summary: 'done', task_id: 'task-1' })
    );
    view.unmount();
    vi.unstubAllGlobals();
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
    const client = await import('../api/client');
    const statusSpy = vi.spyOn(client, 'getBgStatus').mockResolvedValue({
      task_id: 'task-1',
      status: 'transcribing',
      stage: 'transcribing',
      progress: 40,
    });

    const view = render(
      <TaskEventsProvider>
        <TestComponent taskId="task-1" onReady={() => undefined} />
      </TaskEventsProvider>
    );

    await waitFor(() => expect(instances).toHaveLength(1));
    act(() => instances[0].onopen?.());
    vi.useFakeTimers();
    try {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000);
      });
      expect(statusSpy).not.toHaveBeenCalled();

      act(() => instances[0].onerror?.());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_500);
      });
      expect(statusSpy).toHaveBeenCalledTimes(1);

      act(() => instances.at(-1)?.onopen?.());
      await act(async () => {
        await Promise.resolve();
      });
      expect(statusSpy).toHaveBeenCalledTimes(2);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000);
      });
      expect(statusSpy).toHaveBeenCalledTimes(2);
    } finally {
      view.unmount();
      vi.useRealTimers();
      vi.unstubAllGlobals();
    }
  });

  it('tolerates transient polling errors before failing the task', async () => {
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
    const client = await import('../api/client');
    const statusSpy = vi
      .spyOn(client, 'getBgStatus')
      .mockRejectedValueOnce(new Error('temporary outage'))
      .mockRejectedValueOnce(new Error('temporary outage'))
      .mockResolvedValue({
        task_id: 'task-1',
        status: 'transcribing',
        stage: 'transcribing',
        progress: 50,
      });
    const onFailure = vi.fn();

    vi.useFakeTimers();
    const view = render(
      <TaskEventsProvider>
        <TestComponent
          taskId="task-1"
          onReady={(state) => {
            if (state.error) onFailure(state.error);
          }}
        />
      </TaskEventsProvider>
    );

    try {
      expect(instances).toHaveLength(1);
      act(() => instances[0].onerror?.());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(21_500);
      });
      expect(statusSpy).toHaveBeenCalledTimes(3);
      expect(onFailure).not.toHaveBeenCalled();
    } finally {
      view.unmount();
      vi.useRealTimers();
      vi.unstubAllGlobals();
    }
  });
});

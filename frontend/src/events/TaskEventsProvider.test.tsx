import React from 'react';
import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TaskEvent } from '../lib/taskEvents';

import { TaskEventsProvider, useTaskEvents } from './TaskEventsProvider';

describe('TaskEventsProvider', () => {
  it('fans out one EventSource connection with task filtering', () => {
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
    const allEvents: TaskEvent[] = [];
    const taskEvents: TaskEvent[] = [];
    const connectionStates: string[] = [];

    function Consumer() {
      connectionStates.push(useTaskEvents((event) => allEvents.push(event)));
      useTaskEvents((event) => taskEvents.push(event), 'task-1');
      return null;
    }

    const view = render(
      <TaskEventsProvider>
        <Consumer />
      </TaskEventsProvider>
    );

    expect(instances).toHaveLength(1);
    expect(connectionStates.at(-1)).toBe('connecting');
    act(() => instances[0].onopen?.());
    expect(connectionStates.at(-1)).toBe('open');
    act(() => {
      instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'task.event',
          task_id: 'task-2',
          event_type: 'progress',
          payload: { progress: 50 },
        }),
      } as MessageEvent);
    });

    expect(allEvents).toHaveLength(1);
    expect(taskEvents).toHaveLength(0);
    act(() => {
      instances[0].onmessage?.({ data: '{' } as MessageEvent);
      instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'task.event',
          task_id: 'task-1',
          event_type: 'status',
          payload: { status: 'formatting' },
        }),
      } as MessageEvent);
    });

    expect(allEvents).toHaveLength(2);
    expect(taskEvents).toHaveLength(1);
    expect(taskEvents[0].event_type).toBe('status');
    act(() => instances[0].onerror?.());
    expect(connectionStates.at(-1)).toBe('error');
    view.unmount();
    expect(instances[0].close).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
});

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
    expect(instances[0].close).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('opens a new EventSource after the previous connection closes', () => {
    const instances: MockEventSource[] = [];

    class MockEventSource {
      onmessage: ((event: MessageEvent) => void) | null = null;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn();
      readyState = 1;

      constructor() {
        instances.push(this);
      }
    }

    vi.stubGlobal('EventSource', MockEventSource);
    vi.useFakeTimers();
    const connectionStates: string[] = [];

    function Consumer() {
      connectionStates.push(useTaskEvents(() => undefined));
      return null;
    }

    const view = render(
      <TaskEventsProvider>
        <Consumer />
      </TaskEventsProvider>
    );

    act(() => instances[0].onopen?.());
    expect(connectionStates.at(-1)).toBe('open');
    act(() => {
      instances[0].readyState = 2;
      instances[0].onerror?.();
    });
    expect(connectionStates.at(-1)).toBe('error');
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(instances).toHaveLength(2);
    act(() => instances[1].onopen?.());
    expect(connectionStates.at(-1)).toBe('open');
    view.unmount();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('marks a browser-retried EventSource failure as error without closing it', () => {
    const instances: MockEventSource[] = [];

    class MockEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn();
      readyState = 0;

      constructor() {
        instances.push(this);
      }
    }

    vi.stubGlobal('EventSource', MockEventSource);
    const connectionStates: string[] = [];

    function Consumer() {
      connectionStates.push(useTaskEvents(() => undefined));
      return null;
    }

    const view = render(
      <TaskEventsProvider>
        <Consumer />
      </TaskEventsProvider>
    );

    act(() => instances[0].onerror?.());
    expect(connectionStates.at(-1)).toBe('error');
    expect(instances[0].close).not.toHaveBeenCalled();
    act(() => instances[0].onopen?.());
    expect(connectionStates.at(-1)).toBe('open');
    view.unmount();
    vi.unstubAllGlobals();
  });

  it('falls back to polling if the EventSource stays connecting', () => {
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
    vi.useFakeTimers();
    const connectionStates: string[] = [];

    function Consumer() {
      connectionStates.push(useTaskEvents(() => undefined));
      return null;
    }

    const view = render(
      <TaskEventsProvider>
        <Consumer />
      </TaskEventsProvider>
    );

    expect(connectionStates.at(-1)).toBe('connecting');
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(connectionStates.at(-1)).toBe('error');
    expect(instances).toHaveLength(1);
    view.unmount();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});

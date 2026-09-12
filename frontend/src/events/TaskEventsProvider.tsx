import React, { createContext, useCallback, useContext, useEffect, useRef } from 'react';

import { parseTaskEventData } from '../lib/taskEvents';
import type { TaskEvent } from '../lib/taskEvents';

type TaskEventListener = (event: TaskEvent) => void;
type Subscription = {
  listener: TaskEventListener;
  taskId?: string;
};
type Subscribe = (listener: TaskEventListener, taskId?: string) => () => void;

const TaskEventsContext = createContext<Subscribe | null>(null);

export function TaskEventsProvider({ children }: { children: React.ReactNode }) {
  const subscriptionsRef = useRef(new Set<Subscription>());

  const subscribe = useCallback<Subscribe>((listener, taskId) => {
    const subscription = { listener, taskId };
    subscriptionsRef.current.add(subscription);
    return () => subscriptionsRef.current.delete(subscription);
  }, []);

  useEffect(() => {
    if (typeof EventSource === 'undefined') return;
    const base = import.meta.env.VITE_API_BASE || '/api';
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource(`${base}/bg/events`);
      eventSource.onmessage = (message) => {
        const event = parseTaskEventData(message.data);
        if (!event) return;
        for (const subscription of subscriptionsRef.current) {
          if (!subscription.taskId || subscription.taskId === event.task_id) {
            subscription.listener(event);
          }
        }
      };
    } catch {
      return;
    }
    return () => eventSource?.close();
  }, []);

  return <TaskEventsContext.Provider value={subscribe}>{children}</TaskEventsContext.Provider>;
}

export function useTaskEvents(listener: TaskEventListener, taskId?: string | null) {
  const subscribe = useContext(TaskEventsContext);
  if (!subscribe) {
    throw new Error('useTaskEvents must be used within TaskEventsProvider');
  }
  const listenerRef = useRef(listener);
  listenerRef.current = listener;

  useEffect(() => {
    if (taskId === null) return;
    return subscribe((event) => listenerRef.current(event), taskId);
  }, [subscribe, taskId]);
}

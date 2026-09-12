import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

import { API_BASE } from '../lib/apiConfig';
import { parseTaskEventData } from '../lib/taskEvents';
import type { TaskEvent } from '../lib/taskEvents';

type TaskEventListener = (event: TaskEvent) => void;
type Subscription = {
  listener: TaskEventListener;
  taskId?: string;
};
type Subscribe = (listener: TaskEventListener, taskId?: string) => () => void;
export type TaskEventsConnectionState = 'connecting' | 'open' | 'error' | 'unavailable';
type TaskEventsContextValue = {
  subscribe: Subscribe;
  connectionState: TaskEventsConnectionState;
};

const TaskEventsContext = createContext<TaskEventsContextValue | null>(null);

export function TaskEventsProvider({ children }: { children: React.ReactNode }) {
  const subscriptionsRef = useRef(new Set<Subscription>());
  const [connectionState, setConnectionState] = useState<TaskEventsConnectionState>(
    typeof EventSource === 'undefined' ? 'unavailable' : 'connecting'
  );

  const subscribe = useCallback<Subscribe>((listener, taskId) => {
    const subscription = { listener, taskId };
    subscriptionsRef.current.add(subscription);
    return () => subscriptionsRef.current.delete(subscription);
  }, []);

  useEffect(() => {
    if (typeof EventSource === 'undefined') {
      setConnectionState('unavailable');
      return;
    }
    let eventSource: EventSource | null = null;
    try {
      setConnectionState('connecting');
      eventSource = new EventSource(`${API_BASE}/bg/events`);
      eventSource.onopen = () => setConnectionState('open');
      eventSource.onerror = () => setConnectionState('error');
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
      setConnectionState('unavailable');
      return;
    }
    return () => eventSource?.close();
  }, []);

  return (
    <TaskEventsContext.Provider value={{ subscribe, connectionState }}>
      {children}
    </TaskEventsContext.Provider>
  );
}

export function useTaskEvents(listener: TaskEventListener, taskId?: string | null) {
  const context = useContext(TaskEventsContext);
  if (!context) {
    throw new Error('useTaskEvents must be used within TaskEventsProvider');
  }
  const { subscribe, connectionState } = context;
  const listenerRef = useRef(listener);
  listenerRef.current = listener;

  useEffect(() => {
    if (taskId === null) return;
    return subscribe((event) => listenerRef.current(event), taskId);
  }, [subscribe, taskId]);

  return connectionState;
}

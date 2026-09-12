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

const SSE_URL = `${API_BASE}/bg/events`;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;

function reconnectDelay(attempt: number): number {
  return Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
}

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

    let stopped = false;
    let eventSource: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let attempt = 0;
    let generation = 0;

    const clearReconnectTimer = () => {
      if (reconnectTimer == null) return;
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    };

    const connect = () => {
      if (stopped) return;
      clearReconnectTimer();
      eventSource?.close();
      const current = ++generation;
      try {
        if (attempt === 0) setConnectionState('connecting');
        else setConnectionState('error');
        eventSource = new EventSource(SSE_URL);
      } catch {
        setConnectionState('unavailable');
        return;
      }

      eventSource.onopen = () => {
        if (stopped || current !== generation) return;
        attempt = 0;
        setConnectionState('open');
      };
      eventSource.onerror = () => {
        if (stopped || current !== generation) return;
        if (eventSource?.readyState === 0) {
          // EventSource.CONNECTING: the browser is retrying this connection
          setConnectionState('connecting');
          return;
        }
        eventSource?.close();
        eventSource = null;
        setConnectionState('error');
        reconnectTimer = window.setTimeout(() => {
          attempt += 1;
          connect();
        }, reconnectDelay(attempt));
      };
      eventSource.onmessage = (message) => {
        if (stopped || current !== generation) return;
        const event = parseTaskEventData(message.data);
        if (!event) return;
        for (const subscription of subscriptionsRef.current) {
          if (!subscription.taskId || subscription.taskId === event.task_id) {
            subscription.listener(event);
          }
        }
      };
    };

    connect();
    const onOnline = () => {
      attempt = 0;
      connect();
    };
    window.addEventListener('online', onOnline);

    return () => {
      stopped = true;
      generation += 1;
      clearReconnectTimer();
      window.removeEventListener('online', onOnline);
      eventSource?.close();
    };
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

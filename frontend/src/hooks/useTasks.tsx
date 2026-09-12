import { useCallback, useEffect, useState } from 'react';

import { getBgTasks } from '../api/client';
import { applyTaskEvent, parseTaskListResponse } from '../lib/taskState';
import type { TaskListItem } from '../lib/taskState';
import { useToast } from '../components/ToastProvider';
import { useTaskEvents } from '../events/TaskEventsProvider';

const FALLBACK_POLL_INTERVAL_MS = 30_000;

export function useTasks() {
  const [tasks, setTasks] = useState<TaskListItem[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);
  const { addToast } = useToast();

  const load = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
        setError(null);
      }
      try {
        const nextTasks = await getBgTasks();
        setTasks(nextTasks);
        try {
          localStorage.setItem('cached_tasks', JSON.stringify(nextTasks));
        } catch {
          // localStorage cache is optional
        }
      } catch (e: unknown) {
        if (silent) return;
        setError(e);
        try {
          const cached = localStorage.getItem('cached_tasks');
          if (cached) {
            const parsed = parseTaskListResponse(JSON.parse(cached));
            if (parsed) setTasks(parsed);
          }
        } catch {
          // cached_tasks may be missing or invalid JSON
        }

        addToast('Failed to load history', {
          level: 'error',
          actionLabel: 'Retry',
          action: () => {
            load();
          },
        });
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [addToast]
  );

  const eventConnectionState = useTaskEvents((data) => {
    setTasks((prev) => {
      if (!prev) return prev;
      const result = applyTaskEvent(prev, data);
      if (result.shouldReload) setTimeout(() => load(), 0);
      return result.tasks;
    });
  });

  useEffect(() => {
    if (eventConnectionState !== 'error' && eventConnectionState !== 'unavailable') {
      return;
    }
    const interval = window.setInterval(() => {
      void load(true);
    }, FALLBACK_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [eventConnectionState, load]);

  useEffect(() => {
    void load();
    const onTaskChanged = () => void load();
    window.addEventListener('app:task-changed', onTaskChanged);
    const onOnline = () => void load();
    window.addEventListener('online', onOnline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('app:task-changed', onTaskChanged);
    };
  }, [load]);

  return { tasks, loading, error, reload: load };
}

export default useTasks;

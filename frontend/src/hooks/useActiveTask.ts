import { useCallback, useEffect, useRef, useState } from 'react';

import { getBgResult, getBgStatus } from '../api/client';
import { useTaskEvents } from '../events/TaskEventsProvider';
import sanitizeError from '../lib/sanitizeError';
import { taskStageFromStatus, taskStageToIndex } from '../lib/taskEvents';
import type { TaskEvent } from '../lib/taskEvents';
import { applyActiveTaskEvent, shapeTaskResult } from '../lib/taskState';
import type { TaskListItem } from '../lib/taskState';

const FALLBACK_POLL_INITIAL_MS = 1_500;
const FALLBACK_POLL_INTERVAL_MS = 10_000;

export type UseActiveTaskOptions = {
  onStageIndex?: (index: number) => void;
  onResult?: (result: unknown) => void;
  onFailure?: (message: string) => void;
  onCancelled?: () => void;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function createPendingTask(taskId: string): TaskListItem {
  return { id: taskId, status: 'pending', stage: 'pending', progress: 0 };
}

export function useActiveTask(taskId: string | null, options: UseActiveTaskOptions = {}) {
  const [task, setTask] = useState<TaskListItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastErrorDetails, setLastErrorDetails] = useState<string | null>(null);
  const pollRef = useRef<number | null>(0);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = 0;
    }
  }, []);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      return;
    }
    setTask(createPendingTask(taskId));
    setError(null);
    setLastErrorDetails(null);
  }, [taskId]);

  const failTask = useCallback(
    (message: string, details?: unknown) => {
      stopPolling();
      setError(message);
      setLastErrorDetails(sanitizeError(details ?? message));
      optionsRef.current.onStageIndex?.(-1);
      optionsRef.current.onFailure?.(message);
      window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message } }));
    },
    [stopPolling]
  );

  const completeTask = useCallback(
    async (id: string, eventResult?: unknown) => {
      const response = eventResult === undefined ? await getBgResult(id) : eventResult;
      const result =
        eventResult === undefined && isRecord(response) && 'result' in response
          ? response.result
          : response;
      const structured = shapeTaskResult(result, id);
      stopPolling();
      optionsRef.current.onStageIndex?.(4);
      optionsRef.current.onResult?.(structured);
    },
    [stopPolling]
  );

  const applyEvent = useCallback(
    (event: TaskEvent) => {
      setTask((prev) => {
        const current = prev ?? createPendingTask(event.task_id);
        return applyActiveTaskEvent(current, event) ?? current;
      });

      if (event.event_type === 'progress') {
        return;
      }
      if (event.event_type === 'status') {
        const stage = event.stage ?? taskStageFromStatus(event.payload.status);
        const index = taskStageToIndex(stage);
        optionsRef.current.onStageIndex?.(index);
        if (index >= 4 && taskId) {
          void completeTask(taskId);
        }
        return;
      }
      if (event.event_type === 'success' && taskId) {
        void completeTask(taskId, event.payload.result);
        return;
      }
      if (event.event_type === 'failure') {
        failTask(event.payload.error || 'Task failed');
        return;
      }
      if (event.event_type === 'cancelled') {
        stopPolling();
        optionsRef.current.onStageIndex?.(-1);
        optionsRef.current.onCancelled?.();
      }
    },
    [completeTask, failTask, stopPolling, taskId]
  );

  const eventConnectionState = useTaskEvents(applyEvent, taskId);
  const hasOpenedEvents = useRef(false);

  useEffect(() => {
    hasOpenedEvents.current = false;
  }, [taskId]);

  const pollTaskStatus = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const statusResponse = await getBgStatus(id);
        const status = statusResponse.status || '';
        const backendError = statusResponse.error;

        if (backendError || statusResponse.stage === 'failed') {
          failTask(backendError ? String(backendError) : 'Task failed', backendError || status);
          return true;
        }

        const stage = statusResponse.stage ?? taskStageFromStatus(status);
        const index = taskStageToIndex(stage);
        setTask((prev) => ({
          ...(prev ?? createPendingTask(id)),
          status,
          stage,
          progress: statusResponse.progress ?? prev?.progress ?? null,
          error: statusResponse.error,
        }));
        optionsRef.current.onStageIndex?.(index);
        if (index >= 4) {
          await completeTask(id);
          return true;
        }
        return false;
      } catch (pollError) {
        console.warn('poll error', pollError);
        const detail = pollError instanceof Error ? pollError.message : String(pollError);
        failTask(detail, pollError);
        return true;
      }
    },
    [completeTask, failTask]
  );

  useEffect(() => {
    if (!taskId || eventConnectionState !== 'open') return;
    if (!hasOpenedEvents.current) {
      hasOpenedEvents.current = true;
      return;
    }
    void pollTaskStatus(taskId);
  }, [eventConnectionState, pollTaskStatus, taskId]);

  useEffect(() => {
    stopPolling();
    if (!taskId || eventConnectionState === 'open' || eventConnectionState === 'connecting') {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      const terminal = await pollTaskStatus(taskId);
      if (!cancelled && !terminal) {
        pollRef.current = window.setTimeout(poll, FALLBACK_POLL_INTERVAL_MS);
      }
    };
    pollRef.current = window.setTimeout(poll, FALLBACK_POLL_INITIAL_MS);

    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [eventConnectionState, pollTaskStatus, stopPolling, taskId]);

  const activeIndex = taskStageToIndex(task?.stage ?? taskStageFromStatus(task?.status));
  const transcribeProgress =
    activeIndex >= 0 && activeIndex < 3 && typeof task?.progress === 'number'
      ? Math.round(task.progress)
      : null;

  return {
    task,
    activeIndex,
    transcribeProgress,
    error,
    lastErrorDetails,
    connectionState: eventConnectionState,
    stopPolling,
  };
}

export default useActiveTask;

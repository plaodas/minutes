import type { TaskEventPayload, TaskHistoryRecord, TaskListItemResponse } from '../api/types';

import { taskStageFromStatus } from './taskEvents';
import type { TaskEvent } from './taskEvents';

export type TaskHistoryPreview = Partial<TaskHistoryRecord> & {
  event_type?: string;
  payload?: TaskEventPayload & {
    result?: {
      output_file?: string;
      [key: string]: unknown;
    };
  };
};

export type TaskListItem = Partial<Omit<TaskListItemResponse, 'id'>> & {
  id: string;
  error?: string | null;
  histories?: TaskHistoryPreview[];
};

export type HistoryItem = {
  id: string;
  name: string;
  created_at?: string | null;
  status?: string;
  progress?: number | null;
  result?: unknown;
  histories: TaskHistoryPreview[];
  event_count: number;
  latest?: TaskHistoryPreview;
};

export type ApplyTaskEventResult = {
  tasks: TaskListItem[];
  shouldReload: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseTaskListResponse(value: unknown): TaskListItem[] | null {
  const tasks = Array.isArray(value)
    ? value
    : isRecord(value) && Array.isArray(value.tasks)
      ? value.tasks
      : null;
  if (!tasks || !tasks.every((task) => isRecord(task) && typeof task.id === 'string')) {
    return null;
  }
  return tasks as TaskListItem[];
}

export function parseTaskHistoryResponse(value: unknown): TaskHistoryPreview[] | null {
  if (!isRecord(value) || typeof value.task_id !== 'string' || !Array.isArray(value.events)) {
    return null;
  }
  const valid = value.events.every(
    (event) =>
      isRecord(event) &&
      typeof event.event_type === 'string' &&
      (event.event_ts === undefined ||
        event.event_ts === null ||
        typeof event.event_ts === 'string') &&
      (event.payload === undefined || isRecord(event.payload))
  );
  return valid ? (value.events as TaskHistoryPreview[]) : null;
}

function uploadFilename(result: unknown): string | undefined {
  if (typeof result !== 'object' || result === null || Array.isArray(result)) return;
  const filename = (result as Record<string, unknown>).upload_filename;
  return typeof filename === 'string' && filename ? filename : undefined;
}

export function toHistoryItem(task: TaskListItem): HistoryItem {
  return {
    id: task.id,
    name: task.name || uploadFilename(task.result) || `task-${task.id.slice(0, 8)}`,
    created_at: task.created_at,
    status: task.status,
    progress: task.progress,
    result: task.result,
    histories: (task.preview_events || task.histories || []).slice(0, 3),
    event_count: task.event_count || 0,
  };
}

export function shapeTaskResult(result: unknown, taskId: string): unknown {
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const record = result as Record<string, unknown>;
    return { ...record, task_id: 'task_id' in record ? record.task_id : taskId };
  }
  return result;
}

export function applyActiveTaskEvent(task: TaskListItem, event: TaskEvent): TaskListItem | null {
  const result = applyTaskEvent([task], event);
  if (event.event_type === 'deleted_hard') {
    return null;
  }
  return result.tasks[0] ?? task;
}

function createdTaskFromEvent(event: TaskEvent): TaskListItem {
  const status =
    typeof event.payload.status === 'string' && event.payload.status
      ? event.payload.status
      : 'pending';
  const name =
    typeof event.payload.name === 'string' && event.payload.name.trim()
      ? event.payload.name.trim()
      : undefined;
  return {
    id: event.task_id,
    status,
    stage: event.stage ?? taskStageFromStatus(status) ?? 'pending',
    progress: 0,
    ...(name ? { name } : {}),
  };
}

function renameFromEvent(event: TaskEvent): string | null {
  const name = event.payload.name;
  if (typeof name !== 'string') return null;
  const trimmed = name.trim();
  return trimmed || null;
}

export function applyTaskEvent(tasks: TaskListItem[], event: TaskEvent): ApplyTaskEventResult {
  const index = tasks.findIndex((task) => String(task.id) === String(event.task_id));
  if (index === -1) {
    if (event.event_type === 'created') {
      return {
        tasks: [createdTaskFromEvent(event), ...tasks],
        shouldReload: true,
      };
    }
    return { tasks, shouldReload: true };
  }

  if (event.event_type === 'deleted_hard') {
    return {
      tasks: tasks.filter((task) => String(task.id) !== String(event.task_id)),
      shouldReload: true,
    };
  }

  let task = tasks[index];
  let shouldReload = false;

  if (event.event_type === 'progress') {
    task = { ...task, progress: event.payload.progress };
  } else if (event.event_type === 'status') {
    task = {
      ...task,
      status: event.payload.status,
      stage: event.stage ?? taskStageFromStatus(event.payload.status) ?? task.stage,
    };
  } else if (event.event_type === 'success') {
    task = {
      ...task,
      status: 'success',
      stage: event.stage ?? 'success',
      progress: 100,
      ...(event.payload.result !== undefined ? { result: event.payload.result } : {}),
    };
    shouldReload = true;
  } else if (event.event_type === 'failure') {
    task = {
      ...task,
      status: 'failed',
      stage: event.stage ?? 'failed',
      error: event.payload.error,
    };
    shouldReload = true;
  } else if (event.event_type === 'cancelled') {
    task = {
      ...task,
      status: 'cancelled',
      stage: event.stage ?? 'cancelled',
    };
    shouldReload = true;
  } else if (event.event_type === 'deleted') {
    task = {
      ...task,
      status: 'deleted',
      stage: event.stage ?? 'deleted',
    };
    shouldReload = true;
  } else if (event.event_type === 'undeleted') {
    const status = event.payload.status;
    if (!status) return { tasks, shouldReload: true };
    task = {
      ...task,
      status,
      stage: event.stage ?? taskStageFromStatus(status) ?? task.stage,
    };
    shouldReload = true;
  } else if (event.event_type === 'rename') {
    const name = renameFromEvent(event);
    if (!name) return { tasks, shouldReload: true };
    task = { ...task, name };
  } else if (event.event_type === 'created') {
    const created = createdTaskFromEvent(event);
    task = {
      ...task,
      status: created.status,
      stage: created.stage,
      ...(created.name ? { name: created.name } : {}),
    };
  } else {
    return { tasks, shouldReload: false };
  }

  const nextTasks = tasks.slice();
  nextTasks[index] = task;
  return { tasks: nextTasks, shouldReload };
}

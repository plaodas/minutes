import { taskStageFromStatus } from './taskEvents';
import type { TaskEvent, TaskStage } from './taskEvents';

export type TaskHistoryPreview = {
  event_ts?: string | null;
  event_type?: string;
  payload?: {
    error?: string;
    result?: {
      output_file?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type TaskListItem = {
  id: string;
  name?: string | null;
  status?: string;
  stage?: TaskStage;
  progress?: number | null;
  result?: unknown;
  error?: string | null;
  created_at?: string | null;
  last_success_ts?: string | null;
  preview_events?: TaskHistoryPreview[];
  histories?: TaskHistoryPreview[];
  event_count?: number;
  [key: string]: unknown;
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

export function applyTaskEvent(tasks: TaskListItem[], event: TaskEvent): ApplyTaskEventResult {
  const index = tasks.findIndex((task) => String(task.id) === String(event.task_id));
  if (index === -1) {
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
  } else {
    return { tasks, shouldReload: false };
  }

  const nextTasks = tasks.slice();
  nextTasks[index] = task;
  return { tasks: nextTasks, shouldReload };
}

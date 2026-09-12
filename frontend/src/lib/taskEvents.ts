import type { TaskEvent, TaskEventPayload, TaskEventType, TaskStage } from '../api/types';

export type { TaskEvent, TaskEventPayload, TaskEventType, TaskStage };

export const taskStages = [
  'pending',
  'preprocess',
  'transcribing',
  'formatting',
  'success',
  'failed',
  'cancelled',
  'deleted',
] as const satisfies readonly TaskStage[];

export const taskEventTypes = [
  'created',
  'status',
  'progress',
  'success',
  'failure',
  'cancelled',
  'rename',
  'deleted',
  'undeleted',
  'deleted_hard',
] as const satisfies readonly TaskEventType[];

/** Keep in sync with minutes.schemas.STATUS_STAGE_ALIASES. */
export const statusStageAliases = {
  created: 'pending',
  queued: 'pending',
  upload: 'pending',
  uploading: 'pending',
  pre: 'preprocess',
  'pre-processing': 'preprocess',
  recognize: 'transcribing',
  recognizing: 'transcribing',
  format: 'formatting',
  done: 'success',
  finished: 'success',
  completed: 'success',
  failure: 'failed',
} as const satisfies Record<string, TaskStage>;

const stageSet = new Set<string>(taskStages);
const eventTypeSet = new Set<string>(taskEventTypes);
const stageAliasSet = statusStageAliases as Record<string, TaskStage>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function taskStageFromStatus(
  status: TaskStage | string | null | undefined
): TaskStage | undefined {
  if (status == null || status === '') return undefined;
  if (stageSet.has(status)) return status as TaskStage;
  const normalized = String(status).trim().toLowerCase().split(':', 1)[0];
  if (stageSet.has(normalized)) return normalized as TaskStage;
  return stageAliasSet[normalized];
}

export function taskStageToIndex(stage: TaskStage | undefined): number {
  switch (stage) {
    case 'pending':
      return 0;
    case 'preprocess':
      return 1;
    case 'transcribing':
      return 2;
    case 'formatting':
      return 3;
    case 'success':
      return 4;
    default:
      return -1;
  }
}

export function parseTaskEvent(value: unknown): TaskEvent | null {
  if (!isRecord(value) || value.type !== 'task.event') return null;
  if (typeof value.task_id !== 'string') return null;
  if (typeof value.event_type !== 'string' || !eventTypeSet.has(value.event_type)) return null;
  if (!isRecord(value.payload)) return null;
  if (value.stage != null && (typeof value.stage !== 'string' || !stageSet.has(value.stage))) {
    return null;
  }
  if (value.event_type === 'status' && typeof value.payload.status !== 'string') return null;
  if (
    value.event_type === 'progress' &&
    (typeof value.payload.progress !== 'number' || !Number.isFinite(value.payload.progress))
  ) {
    return null;
  }
  return value as TaskEvent;
}

export function parseTaskEventData(data: string): TaskEvent | null {
  try {
    return parseTaskEvent(JSON.parse(data));
  } catch {
    // SSE payload was not JSON
    return null;
  }
}

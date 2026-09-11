export const taskStages = [
  'pending',
  'preprocess',
  'transcribing',
  'formatting',
  'success',
  'failed',
  'cancelled',
  'deleted',
] as const

export type TaskStage = typeof taskStages[number]

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
] as const

export type TaskEventType = typeof taskEventTypes[number]

export type TaskEventPayload = {
  status?: string
  progress?: number
  result?: unknown
  error?: string
  name?: string
  previous?: string
  [key: string]: unknown
}

type TaskEventBase = {
  type: 'task.event'
  task_id: string
  stage?: TaskStage
}

export type TaskEvent = TaskEventBase & (
  | { event_type: 'status'; payload: TaskEventPayload & { status: string } }
  | { event_type: 'progress'; payload: TaskEventPayload & { progress: number } }
  | {
      event_type: Exclude<TaskEventType, 'status' | 'progress'>
      payload: TaskEventPayload
    }
)

const stageSet = new Set<string>(taskStages)
const eventTypeSet = new Set<string>(taskEventTypes)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function taskStageFromStatus(status: string | undefined): TaskStage | undefined {
  if (!status) return undefined
  const normalized = status.trim().toLowerCase().split(':', 1)[0]
  if (stageSet.has(normalized)) return normalized as TaskStage
  const aliases: Record<string, TaskStage> = {
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
  }
  return aliases[normalized]
}

export function taskStageToIndex(stage: TaskStage | undefined): number {
  switch (stage) {
    case 'pending': return 0
    case 'preprocess': return 1
    case 'transcribing': return 2
    case 'formatting': return 3
    case 'success': return 4
    default: return -1
  }
}

export function parseTaskEvent(value: unknown): TaskEvent | null {
  if (!isRecord(value) || value.type !== 'task.event') return null
  if (typeof value.task_id !== 'string') return null
  if (typeof value.event_type !== 'string' || !eventTypeSet.has(value.event_type)) return null
  if (!isRecord(value.payload)) return null
  if (value.stage !== undefined && (typeof value.stage !== 'string' || !stageSet.has(value.stage))) return null
  if (value.event_type === 'status' && typeof value.payload.status !== 'string') return null
  if (value.event_type === 'progress' && (typeof value.payload.progress !== 'number' || !Number.isFinite(value.payload.progress))) return null
  return value as TaskEvent
}

export function parseTaskEventData(data: string): TaskEvent | null {
  try {
    return parseTaskEvent(JSON.parse(data))
  } catch {
    return null
  }
}

import { taskStageFromStatus } from './taskEvents'
import type { TaskEvent, TaskStage } from './taskEvents'

export type TaskHistoryPreview = {
  event_ts?: string | null
  event_type?: string
  payload?: unknown
  [key: string]: unknown
}

export type TaskListItem = {
  id: string
  name?: string | null
  status?: string
  stage?: TaskStage
  progress?: number | null
  result?: unknown
  created_at?: string | null
  last_success_ts?: string | null
  preview_events?: TaskHistoryPreview[]
  histories?: TaskHistoryPreview[]
  event_count?: number
  [key: string]: unknown
}

export type ApplyTaskEventResult = {
  tasks: TaskListItem[]
  shouldReload: boolean
}

export function applyTaskEvent(
  tasks: TaskListItem[],
  event: TaskEvent,
): ApplyTaskEventResult {
  const index = tasks.findIndex((task) => String(task.id) === String(event.task_id))
  if (index === -1) {
    return { tasks, shouldReload: true }
  }

  let task = tasks[index]
  let shouldReload = false

  if (event.event_type === 'progress') {
    task = { ...task, progress: event.payload.progress }
  } else if (event.event_type === 'status') {
    task = {
      ...task,
      status: event.payload.status,
      stage: event.stage ?? taskStageFromStatus(event.payload.status) ?? task.stage,
    }
  } else if (event.event_type === 'success') {
    task = {
      ...task,
      status: 'success',
      stage: event.stage ?? 'success',
      progress: 100,
      ...(event.payload.result !== undefined ? { result: event.payload.result } : {}),
    }
    shouldReload = true
  } else {
    return { tasks, shouldReload: false }
  }

  const nextTasks = tasks.slice()
  nextTasks[index] = task
  return { tasks: nextTasks, shouldReload }
}

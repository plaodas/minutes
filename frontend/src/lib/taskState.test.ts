import { describe, expect, it } from 'vitest'
import type { TaskEvent } from './taskEvents'
import { applyTaskEvent, parseTaskListResponse, toHistoryItem, type TaskListItem } from './taskState'

const tasks: TaskListItem[] = [
  { id: 'task-1', status: 'transcribing', stage: 'transcribing', progress: 10 },
  { id: 'task-2', status: 'pending', stage: 'pending', progress: 0 },
]

function event(value: Omit<TaskEvent, 'type'>): TaskEvent {
  return { type: 'task.event', ...value } as TaskEvent
}

describe('applyTaskEvent', () => {
  it('immutably applies progress to the matching task', () => {
    const result = applyTaskEvent(tasks, event({
      task_id: 'task-1',
      event_type: 'progress',
      payload: { progress: 42 },
    }))

    expect(result.tasks).not.toBe(tasks)
    expect(result.tasks[0]).toMatchObject({ progress: 42 })
    expect(result.tasks[1]).toBe(tasks[1])
    expect(result.shouldReload).toBe(false)
  })

  it('derives a stage from legacy status events', () => {
    const result = applyTaskEvent(tasks, event({
      task_id: 'task-1',
      event_type: 'status',
      payload: { status: 'formatting' },
    }))

    expect(result.tasks[0]).toMatchObject({ status: 'formatting', stage: 'formatting' })
  })

  it('applies success and requests server reconciliation', () => {
    const result = applyTaskEvent(tasks, event({
      task_id: 'task-1',
      event_type: 'success',
      stage: 'success',
      payload: { result: { summary: 'done' } },
    }))

    expect(result.tasks[0]).toMatchObject({
      status: 'success',
      stage: 'success',
      progress: 100,
      result: { summary: 'done' },
    })
    expect(result.shouldReload).toBe(true)
  })

  it('keeps the list unchanged and requests reload for an unknown task', () => {
    const result = applyTaskEvent(tasks, event({
      task_id: 'unknown',
      event_type: 'created',
      payload: {},
    }))

    expect(result.tasks).toBe(tasks)
    expect(result.shouldReload).toBe(true)
  })
})

describe('toHistoryItem', () => {
  it('uses the upload filename when the task has no explicit name', () => {
    const item = toHistoryItem({
      id: '123456789',
      result: { upload_filename: 'planning.wav' },
    })

    expect(item.name).toBe('planning.wav')
  })

  it('supports legacy histories and limits previews to three events', () => {
    const histories = [
      { event_type: 'created' },
      { event_type: 'status' },
      { event_type: 'progress' },
      { event_type: 'success' },
    ]
    const item = toHistoryItem({ id: 'task-1', histories })

    expect(item.histories).toEqual(histories.slice(0, 3))
    expect(item.event_count).toBe(0)
  })
})

describe('parseTaskListResponse', () => {
  it('accepts wrapped API responses and legacy cached arrays', () => {
    expect(parseTaskListResponse({ tasks: [{ id: 'api-task' }] })).toEqual([{ id: 'api-task' }])
    expect(parseTaskListResponse([{ id: 'cached-task' }])).toEqual([{ id: 'cached-task' }])
  })

  it('rejects malformed task lists', () => {
    expect(parseTaskListResponse({ tasks: [{ status: 'pending' }] })).toBeNull()
    expect(parseTaskListResponse({ tasks: 'invalid' })).toBeNull()
  })
})

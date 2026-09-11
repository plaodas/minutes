import { describe, expect, it } from 'vitest'
import { parseTaskEvent, parseTaskEventData, taskStageFromStatus, taskStageToIndex } from './taskEvents'

describe('task event contract', () => {
  it('normalizes detailed transcription status', () => {
    expect(taskStageFromStatus('transcribing:48.3s')).toBe('transcribing')
    expect(taskStageToIndex('transcribing')).toBe(2)
  })

  it('accepts typed status events from new and old servers', () => {
    expect(parseTaskEvent({
      type: 'task.event',
      task_id: 'task-id',
      event_type: 'status',
      stage: 'formatting',
      payload: { status: 'formatting' },
    })?.stage).toBe('formatting')
    expect(parseTaskEvent({
      type: 'task.event',
      task_id: 'task-id',
      event_type: 'status',
      payload: { status: 'formatting' },
    })).not.toBeNull()
  })

  it('rejects malformed events', () => {
    expect(parseTaskEventData('{')).toBeNull()
    expect(parseTaskEvent({
      type: 'task.event',
      task_id: 'task-id',
      event_type: 'progress',
      payload: { progress: '50' },
    })).toBeNull()
  })
})

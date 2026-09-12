import { describe, expect, it } from 'vitest';

import type { TaskEvent } from './taskEvents';
import {
  applyActiveTaskEvent,
  applyTaskEvent,
  parseTaskHistoryResponse,
  parseTaskListResponse,
  shapeTaskResult,
  toHistoryItem,
  type TaskListItem,
} from './taskState';

const tasks: TaskListItem[] = [
  { id: 'task-1', status: 'transcribing', stage: 'transcribing', progress: 10 },
  { id: 'task-2', status: 'pending', stage: 'pending', progress: 0 },
];

function event(value: Omit<TaskEvent, 'type'>): TaskEvent {
  return { type: 'task.event', ...value } as TaskEvent;
}

describe('applyTaskEvent', () => {
  it('immutably applies progress to the matching task', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'progress',
        payload: { progress: 42 },
      })
    );

    expect(result.tasks).not.toBe(tasks);
    expect(result.tasks[0]).toMatchObject({ progress: 42 });
    expect(result.tasks[1]).toBe(tasks[1]);
    expect(result.shouldReload).toBe(false);
  });

  it('derives a stage from legacy status events', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'status',
        payload: { status: 'formatting' },
      })
    );

    expect(result.tasks[0]).toMatchObject({ status: 'formatting', stage: 'formatting' });
  });

  it('applies success and requests server reconciliation', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'success',
        stage: 'success',
        payload: { result: { summary: 'done' } },
      })
    );

    expect(result.tasks[0]).toMatchObject({
      status: 'success',
      stage: 'success',
      progress: 100,
      result: { summary: 'done' },
    });
    expect(result.shouldReload).toBe(true);
  });

  it('applies failure and preserves the reported error', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'failure',
        stage: 'failed',
        payload: { error: 'transcription failed' },
      })
    );

    expect(result.tasks[0]).toMatchObject({
      status: 'failed',
      stage: 'failed',
      error: 'transcription failed',
    });
    expect(result.shouldReload).toBe(true);
  });

  it('applies cancellation and requests server reconciliation', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'cancelled',
        stage: 'cancelled',
        payload: {},
      })
    );

    expect(result.tasks[0]).toMatchObject({
      status: 'cancelled',
      stage: 'cancelled',
    });
    expect(result.shouldReload).toBe(true);
  });

  it('applies soft deletion and requests server reconciliation', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'deleted',
        stage: 'deleted',
        payload: { previous: 'transcribing' },
      })
    );

    expect(result.tasks[0]).toMatchObject({ status: 'deleted', stage: 'deleted' });
    expect(result.shouldReload).toBe(true);
  });

  it('restores the status carried by an undelete event', () => {
    const deletedTasks: TaskListItem[] = [
      { id: 'task-1', status: 'deleted', stage: 'deleted', progress: 10 },
    ];
    const result = applyTaskEvent(
      deletedTasks,
      event({
        task_id: 'task-1',
        event_type: 'undeleted',
        stage: 'pending',
        payload: { previous: 'deleted', status: 'pending' },
      })
    );

    expect(result.tasks[0]).toMatchObject({ status: 'pending', stage: 'pending' });
    expect(result.shouldReload).toBe(true);
  });

  it('removes a hard-deleted task and requests server reconciliation', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'deleted_hard',
        payload: {},
      })
    );

    expect(result.tasks).toEqual([tasks[1]]);
    expect(result.shouldReload).toBe(true);
  });

  it('inserts a created task and requests server reconciliation', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-3',
        event_type: 'created',
        stage: 'pending',
        payload: { status: 'pending', name: 'kickoff.wav' },
      })
    );

    expect(result.tasks[0]).toMatchObject({
      id: 'task-3',
      name: 'kickoff.wav',
      status: 'pending',
      stage: 'pending',
      progress: 0,
    });
    expect(result.tasks.slice(1)).toEqual(tasks);
    expect(result.shouldReload).toBe(true);
  });

  it('updates a known created task without reloading', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-2',
        event_type: 'created',
        stage: 'pending',
        payload: { status: 'pending' },
      })
    );

    expect(result.tasks[1]).toMatchObject({ id: 'task-2', status: 'pending', stage: 'pending' });
    expect(result.shouldReload).toBe(false);
  });

  it('renames a known task without reloading', () => {
    const named: TaskListItem[] = [
      { id: 'task-1', name: 'old', status: 'success', stage: 'success' },
    ];
    const result = applyTaskEvent(
      named,
      event({
        task_id: 'task-1',
        event_type: 'rename',
        payload: { name: '  planning notes  ' },
      })
    );

    expect(result.tasks[0]).toMatchObject({ name: 'planning notes', status: 'success' });
    expect(result.shouldReload).toBe(false);
  });

  it('requests reload when a rename event has no name', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'task-1',
        event_type: 'rename',
        payload: {},
      })
    );

    expect(result.tasks).toBe(tasks);
    expect(result.shouldReload).toBe(true);
  });

  it('keeps the list unchanged and requests reload for an unknown task', () => {
    const result = applyTaskEvent(
      tasks,
      event({
        task_id: 'unknown',
        event_type: 'status',
        payload: { status: 'transcribing' },
      })
    );

    expect(result.tasks).toBe(tasks);
    expect(result.shouldReload).toBe(true);
  });
});

describe('applyActiveTaskEvent', () => {
  it('updates one task with the shared event rules', () => {
    const next = applyActiveTaskEvent(
      tasks[0],
      event({
        task_id: 'task-1',
        event_type: 'status',
        payload: { status: 'formatting' },
      })
    );

    expect(next).toMatchObject({ status: 'formatting', stage: 'formatting' });
  });

  it('renames the active task with the shared event rules', () => {
    const next = applyActiveTaskEvent(
      { id: 'task-1', name: 'old', status: 'success', stage: 'success' },
      event({
        task_id: 'task-1',
        event_type: 'rename',
        payload: { name: 'new title' },
      })
    );

    expect(next).toMatchObject({ name: 'new title', status: 'success' });
  });
});

describe('shapeTaskResult', () => {
  it('adds the task id when the result object has none', () => {
    expect(shapeTaskResult({ summary: 'done' }, 'task-1')).toEqual({
      summary: 'done',
      task_id: 'task-1',
    });
  });
});

describe('toHistoryItem', () => {
  it('uses the upload filename when the task has no explicit name', () => {
    const item = toHistoryItem({
      id: '123456789',
      result: { upload_filename: 'planning.wav' },
    });

    expect(item.name).toBe('planning.wav');
  });

  it('supports legacy histories and limits previews to three events', () => {
    const histories = [
      { event_type: 'created' },
      { event_type: 'status' },
      { event_type: 'progress' },
      { event_type: 'success' },
    ];
    const item = toHistoryItem({ id: 'task-1', histories });

    expect(item.histories).toEqual(histories.slice(0, 3));
    expect(item.event_count).toBe(0);
  });
});

describe('parseTaskListResponse', () => {
  it('accepts wrapped API responses and legacy cached arrays', () => {
    expect(parseTaskListResponse({ tasks: [{ id: 'api-task' }] })).toEqual([{ id: 'api-task' }]);
    expect(parseTaskListResponse([{ id: 'cached-task' }])).toEqual([{ id: 'cached-task' }]);
  });

  it('rejects malformed task lists', () => {
    expect(parseTaskListResponse({ tasks: [{ status: 'pending' }] })).toBeNull();
    expect(parseTaskListResponse({ tasks: 'invalid' })).toBeNull();
  });
});

describe('parseTaskHistoryResponse', () => {
  it('accepts a typed task events response', () => {
    const events = [{ event_ts: null, event_type: 'created', payload: {} }];
    expect(parseTaskHistoryResponse({ task_id: 'task-1', events })).toEqual(events);
  });

  it('rejects malformed event entries', () => {
    expect(parseTaskHistoryResponse({ task_id: 'task-1', events: 'invalid' })).toBeNull();
    expect(parseTaskHistoryResponse({ task_id: 'task-1', events: [{ payload: {} }] })).toBeNull();
  });
});

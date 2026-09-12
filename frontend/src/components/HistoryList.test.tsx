import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { HistoryItem } from '../lib/taskState';

import HistoryList from './HistoryList';

const items: HistoryItem[] = [
  {
    id: 'task-1',
    name: 'Planning notes',
    created_at: '2026-09-12T00:00:00.000Z',
    status: 'success',
    progress: 100,
    histories: [{ event_type: 'success', event_ts: '2026-09-12T00:00:00.000Z' }],
    event_count: 1,
  },
];

describe('HistoryList', () => {
  it('renders history rows and forwards minutes and events actions', () => {
    const onOpenMinutes = vi.fn();
    const onOpenEvents = vi.fn();

    render(<HistoryList items={items} onOpenMinutes={onOpenMinutes} onOpenEvents={onOpenEvents} />);

    expect(screen.getByText('Planning notes')).toBeTruthy();
    expect(screen.getByTestId('history-list-sentinel')).toBeTruthy();

    fireEvent.click(screen.getByTestId('view-minutes-task-1'));
    expect(onOpenMinutes).toHaveBeenCalledWith('task-1');

    fireEvent.click(screen.getByTestId('view-history-task-1'));
    expect(onOpenEvents).toHaveBeenCalledWith('task-1');
    expect(onOpenMinutes).toHaveBeenCalledTimes(1);
  });
});

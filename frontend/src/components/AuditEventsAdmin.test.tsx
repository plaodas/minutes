import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { listAuditEvents } from '../api/client';

import AuditEventsAdmin from './AuditEventsAdmin';
import { ToastProvider } from './ToastProvider';

vi.mock('../api/client', () => ({
  listAuditEvents: vi.fn(),
}));

const events = [
  {
    id: '2',
    created_at: '2026-10-17T04:00:00',
    action: 'service_token.revoke',
    actor_kind: 'session',
    actor_user_id: 'admin-user',
    actor_token_id: null,
    target_type: 'service_token',
    target_id: 'token-1',
    detail: { name: 'audit-token', user_id: 'admin-user' },
  },
];

describe('AuditEventsAdmin', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.mocked(listAuditEvents).mockReset();
    vi.mocked(listAuditEvents).mockResolvedValue({ events, has_more: false });
  });

  it('shows events and reloads with the selected action and target', async () => {
    render(
      <ToastProvider>
        <AuditEventsAdmin />
      </ToastProvider>
    );

    expect(await screen.findByText('service_token.revoke')).toBeTruthy();
    expect(screen.getByText('actor: session · user: admin-user')).toBeTruthy();
    expect(screen.getByText('service_token: token-1')).toBeTruthy();
    expect(screen.getByText('{"name":"audit-token","user_id":"admin-user"}')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('action'), {
      target: { value: 'task.delete' },
    });
    fireEvent.change(screen.getByLabelText('target type'), {
      target: { value: 'task' },
    });
    fireEvent.change(screen.getByLabelText('target id'), {
      target: { value: 'task-9' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Show' }));

    await waitFor(() => {
      expect(listAuditEvents).toHaveBeenLastCalledWith({
        action: 'task.delete',
        target_type: 'task',
        target_id: 'task-9',
      });
    });
    expect(screen.queryByRole('button', { name: 'Show older' })).toBeNull();
  });

  it('appends the next older page and hides the button when it ends', async () => {
    vi.mocked(listAuditEvents)
      .mockResolvedValueOnce({ events, has_more: true })
      .mockResolvedValueOnce({
        has_more: false,
        events: [
          {
            ...events[0],
            id: '1',
            created_at: '2026-10-17T03:00:00',
            action: 'task.delete',
            detail: null,
          },
        ],
      });

    render(
      <ToastProvider>
        <AuditEventsAdmin />
      </ToastProvider>
    );

    expect(await screen.findByRole('button', { name: 'Show older' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show older' }));

    await waitFor(() => {
      expect(listAuditEvents).toHaveBeenLastCalledWith({
        before_created_at: '2026-10-17T04:00:00',
        before_id: '2',
      });
    });
    expect(screen.getByText('2026-10-17T04:00:00')).toBeTruthy();
    expect(screen.getByText('2026-10-17T03:00:00')).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Show older' })).toBeNull();
    });
  });
});

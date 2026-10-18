import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createServiceToken, listServiceTokens, listUsers } from '../api/client';

import ServiceTokensAdmin from './ServiceTokensAdmin';
import { ToastProvider } from './ToastProvider';

vi.mock('../api/client', () => ({
  listServiceTokens: vi.fn(),
  listUsers: vi.fn(),
  createServiceToken: vi.fn(),
  revokeServiceToken: vi.fn(),
}));

describe('ServiceTokensAdmin', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.mocked(listServiceTokens).mockResolvedValue({
      tokens: [
        {
          id: 'active-id',
          name: 'memoroku',
          user_id: 'user-1',
          username: 'demo',
          revoked: false,
          created_at: '2026-10-17T03:52:47.736003',
        },
        {
          id: 'revoked-id',
          name: null,
          user_id: null,
          revoked: true,
          created_at: '2026-10-17T03:56:58.985600',
        },
      ],
    });
    vi.mocked(listUsers).mockResolvedValue({
      users: [{ id: 'user-1', username: 'demo' }],
    });
  });

  it('shows a revoked label and disables revoke for revoked tokens', async () => {
    render(
      <ToastProvider>
        <ServiceTokensAdmin />
      </ToastProvider>
    );

    expect(await screen.findByText('失効済み')).toBeTruthy();
    expect(screen.getByText('memoroku')).toBeTruthy();
    expect(screen.getByText('revoked-id')).toBeTruthy();

    const revokeButtons = screen.getAllByRole('button', { name: '失効' });
    expect(revokeButtons).toHaveLength(2);
    expect((revokeButtons[0] as HTMLButtonElement).disabled).toBe(false);
    expect((revokeButtons[1] as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('ユーザー: demo · user-1')).toBeTruthy();
  });

  it('creates a token only after a username is selected', async () => {
    vi.mocked(createServiceToken).mockResolvedValue({ token: 'secret', id: 'new-id' });
    const prompt = vi.spyOn(window, 'prompt').mockReturnValue(null);
    render(
      <ToastProvider>
        <ServiceTokensAdmin />
      </ToastProvider>
    );

    const userSelect = await screen.findByRole('combobox', { name: 'ユーザー' });
    expect(screen.getByRole('option', { name: 'demo' })).toBeTruthy();
    expect(screen.queryByPlaceholderText('associate user id (optional)')).toBeNull();
    const createButton = screen.getByRole('button', { name: 'トークンを作成' });
    expect((createButton as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(userSelect, { target: { value: 'user-1' } });
    expect((createButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(createServiceToken).toHaveBeenCalledWith(undefined, 'user-1');
    });
    expect((screen.getByLabelText('作成したサービストークン') as HTMLInputElement).value).toBe(
      'secret'
    );
    expect(prompt).not.toHaveBeenCalled();
  });
});

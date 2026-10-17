import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listServiceTokens } from '../api/client';

import ServiceTokensAdmin from './ServiceTokensAdmin';
import { ToastProvider } from './ToastProvider';

vi.mock('../api/client', () => ({
  listServiceTokens: vi.fn(),
  createServiceToken: vi.fn(),
  revokeServiceToken: vi.fn(),
}));

describe('ServiceTokensAdmin', () => {
  beforeEach(() => {
    vi.mocked(listServiceTokens).mockResolvedValue({
      tokens: [
        {
          id: 'active-id',
          name: 'memoroku',
          user_id: null,
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
  });

  it('shows a revoked label and disables revoke for revoked tokens', async () => {
    render(
      <ToastProvider>
        <ServiceTokensAdmin />
      </ToastProvider>
    );

    expect(await screen.findByText('Revoked')).toBeTruthy();
    expect(screen.getByText('memoroku')).toBeTruthy();
    expect(screen.getByText('revoked-id')).toBeTruthy();

    const revokeButtons = screen.getAllByRole('button', { name: 'Revoke' });
    expect(revokeButtons).toHaveLength(2);
    expect((revokeButtons[0] as HTMLButtonElement).disabled).toBe(false);
    expect((revokeButtons[1] as HTMLButtonElement).disabled).toBe(true);
  });
});

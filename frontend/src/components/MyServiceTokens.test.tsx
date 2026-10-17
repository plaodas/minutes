import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createMyServiceToken, listMyServiceTokens } from '../api/client';

import MyServiceTokens from './MyServiceTokens';
import { ToastProvider } from './ToastProvider';

vi.mock('../api/client', () => ({
  listMyServiceTokens: vi.fn(),
  createMyServiceToken: vi.fn(),
  revokeMyServiceToken: vi.fn(),
}));

describe('MyServiceTokens', () => {
  beforeEach(() => {
    vi.mocked(listMyServiceTokens).mockResolvedValue({ tokens: [] });
  });

  it('creates a token for the current user without a user field', async () => {
    vi.mocked(createMyServiceToken).mockResolvedValue({ token: 'secret', id: 'new-id' });
    vi.spyOn(window, 'prompt').mockReturnValue(null);
    render(
      <ToastProvider>
        <MyServiceTokens />
      </ToastProvider>
    );

    expect(screen.queryByRole('combobox', { name: 'user' })).toBeNull();
    expect(screen.queryByPlaceholderText('associate user id (optional)')).toBeNull();
    fireEvent.change(screen.getByLabelText('トークン名'), { target: { value: 'phone' } });
    fireEvent.click(screen.getByRole('button', { name: 'トークンを作成' }));

    await waitFor(() => {
      expect(createMyServiceToken).toHaveBeenCalledWith('phone');
    });
  });
});

import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CreatedServiceToken from './CreatedServiceToken';
import { ToastProvider } from './ToastProvider';

function renderToken() {
  return render(
    <ToastProvider>
      <CreatedServiceToken token="secret-value" onClose={vi.fn()} />
    </ToastProvider>
  );
}

describe('CreatedServiceToken', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows the token until it is closed', () => {
    const onClose = vi.fn();
    render(
      <ToastProvider>
        <CreatedServiceToken token="secret-value" onClose={onClose} />
      </ToastProvider>
    );

    expect((screen.getByLabelText('作成したサービストークン') as HTMLInputElement).value).toBe(
      'secret-value'
    );
    fireEvent.click(screen.getByRole('button', { name: '閉じる' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('copies the token from the button and leaves it on screen', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    renderToken();

    fireEvent.click(screen.getByRole('button', { name: 'コピー' }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('secret-value');
    });
    expect(await screen.findByText('トークンをクリップボードにコピーしました')).toBeTruthy();
    expect((screen.getByLabelText('作成したサービストークン') as HTMLInputElement).value).toBe(
      'secret-value'
    );
  });

  it('reports failure when clipboard write does not finish', async () => {
    const writeText = vi.fn(() => new Promise<void>(() => {}));
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    renderToken();

    fireEvent.click(screen.getByRole('button', { name: 'コピー' }));

    expect(await screen.findByText('コピーに失敗しました', {}, { timeout: 2000 })).toBeTruthy();
    expect((screen.getByLabelText('作成したサービストークン') as HTMLInputElement).value).toBe(
      'secret-value'
    );
  });

  it('keeps the token visible when copy fails', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    renderToken();

    fireEvent.click(screen.getByRole('button', { name: 'コピー' }));

    expect(await screen.findByText('コピーに失敗しました')).toBeTruthy();
    expect((screen.getByLabelText('作成したサービストークン') as HTMLInputElement).value).toBe(
      'secret-value'
    );
  });
});

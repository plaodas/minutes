import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from './ToastProvider';
import SettingsView from './SettingsView';

function renderSettings() {
  return render(
    <ToastProvider>
      <SettingsView />
    </ToastProvider>
  );
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe('SettingsView', () => {
  it('offers hayamimi for Japanese when the server reports it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', hayamimi: true }),
      })
    );

    renderSettings();

    const engine = await screen.findByLabelText('Japanese transcript engine');
    fireEvent.change(engine, { target: { value: 'hayamimi' } });
    expect(JSON.parse(localStorage.getItem('minutes.settings') || '{}').engine).toBe('hayamimi');

    fireEvent.change(screen.getByLabelText('Transcript language'), {
      target: { value: 'English' },
    });
    await waitFor(() => {
      expect(screen.queryByLabelText('Japanese transcript engine')).toBeNull();
    });
  });

  it('hides the engine and clears a stored hayamimi choice when health is off', async () => {
    localStorage.setItem(
      'minutes.settings',
      JSON.stringify({ language: 'Japanese', includeActions: true, engine: 'hayamimi' })
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', hayamimi: false }),
      })
    );

    renderSettings();

    await waitFor(() => {
      expect(screen.queryByLabelText('Japanese transcript engine')).toBeNull();
      expect(JSON.parse(localStorage.getItem('minutes.settings') || '{}').engine).toBe('whisper');
    });
  });
});

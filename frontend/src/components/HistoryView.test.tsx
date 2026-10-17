import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import HistoryView from './HistoryView';

vi.mock('../hooks/useTasks', () => {
  const tasks: never[] = [];
  return {
    useTasks: () => ({
      tasks,
      loading: false,
      error: null,
      reload: vi.fn(),
    }),
  };
});

vi.mock('./MinutesDrawer', () => ({
  MinutesDrawer: ({ taskId }: { taskId: string }) => (
    <div role="dialog" aria-label={`${taskId} の議事録`} />
  ),
}));

const TASK_ID = 'de487a2c-8ca9-41e6-9399-54f1df804db5';

function renderHistory() {
  return render(<HistoryView onCreate={() => undefined} />);
}

describe('HistoryView minutes links', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState(null, '', '/');
    vi.unstubAllGlobals();
  });

  it('opens the drawer from a pasted minutes link', async () => {
    window.location.hash = `#minutes=${TASK_ID}`;

    renderHistory();

    expect(await screen.findByRole('dialog', { name: `${TASK_ID} の議事録` })).toBeTruthy();
  });

  it('opens the drawer when the minutes hash changes', async () => {
    renderHistory();
    expect(screen.queryByRole('dialog')).toBeNull();

    window.location.hash = `#minutes=${TASK_ID}`;
    window.dispatchEvent(new HashChangeEvent('hashchange'));

    expect(await screen.findByRole('dialog', { name: `${TASK_ID} の議事録` })).toBeTruthy();
  });
});

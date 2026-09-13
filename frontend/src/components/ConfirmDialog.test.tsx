import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ConfirmDialog from './ConfirmDialog';

describe('ConfirmDialog', () => {
  it('portals above a stacked parent so the dialog is not clipped or covered', () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();

    render(
      <div className="fixed inset-0 z-40" data-testid="parent-overlay">
        <div className="relative z-10 bg-white">drawer</div>
        <ConfirmDialog
          open
          title="Delete minutes"
          message="Delete this minutes entry?"
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      </div>
    );

    const dialog = screen.getByTestId('confirm-dialog');
    expect(dialog.parentElement).toBe(document.body);
    expect(dialog.className).toContain('z-[80]');
    expect(screen.getByRole('heading', { name: 'Delete minutes' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import MarkdownBody from './MarkdownBody';

describe('MarkdownBody', () => {
  it('renders headings, bold text, and leaves raw HTML as text', () => {
    const { container } = render(
      <MarkdownBody text={'### 整形済み議事録\n\n**A** です\n\n<script>alert(1)</script>'} />
    );

    expect(screen.getByRole('heading', { name: '整形済み議事録' })).toBeTruthy();
    expect(screen.getByText('A').tagName).toBe('STRONG');
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('alert(1)');
  });
});

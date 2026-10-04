import { describe, expect, test } from 'vitest';

import { formatActionItems } from './minutesResult';

describe('formatActionItems', () => {
  test('removes leftover bold markers from stored action text', () => {
    const text = formatActionItems({
      action_items: [
        { text: 'B（提案者）が**: 来週までに: 社内検討の完了と返答を提出する' },
        { text: 'A（検討担当者）が**: 今月中に: システムの導入判断を行う' },
      ],
    });

    expect(text).toBe(
      [
        'B（提案者）が: 来週までに: 社内検討の完了と返答を提出する',
        'A（検討担当者）が: 今月中に: システムの導入判断を行う',
      ].join('\n')
    );
    expect(text).not.toContain('**');
  });
});

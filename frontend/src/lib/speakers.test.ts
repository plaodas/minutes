import { describe, expect, test } from 'vitest';

import { assignSpeaker, speakerUpdates, transcriptSegments } from './speakers';

describe('speaker updates', () => {
  const segments = transcriptSegments([
    { start: 0, text: 'こんにちは' },
    { start: 2, text: '了解', speaker: '佐藤' },
  ]);

  test('assigns one speaker to selected segments', () => {
    const next = assignSpeaker(segments, [0, 1], '山田');
    expect(next.map((segment) => segment.speaker)).toEqual(['山田', '山田']);
    expect(segments[0].speaker).toBeUndefined();
  });

  test('sends only changed speaker names', () => {
    const next = assignSpeaker(segments, [0], '山田');
    expect(speakerUpdates(segments, next)).toEqual([{ index: 0, speaker: '山田' }]);
  });
});

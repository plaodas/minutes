import { describe, expect, it } from 'vitest';

import { minutesHash, minutesTaskIdFromHash } from './minutesLink';

const TASK_ID = 'de487a2c-8ca9-41e6-9399-54f1df804db5';

describe('minutesTaskIdFromHash', () => {
  it('reads a copied minutes link', () => {
    expect(minutesTaskIdFromHash(minutesHash(TASK_ID))).toBe(TASK_ID);
  });

  it('ignores other hashes', () => {
    expect(minutesTaskIdFromHash('')).toBeNull();
    expect(minutesTaskIdFromHash('#minutes=')).toBeNull();
    expect(minutesTaskIdFromHash('#minutes=not-a-task')).toBeNull();
    expect(minutesTaskIdFromHash('#settings')).toBeNull();
  });
});

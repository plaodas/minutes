import { afterEach, describe, expect, it } from 'vitest';

import {
  API_BASE,
  applyUploadSettings,
  ensureUserId,
  getAuthHeaders,
  getTasksPageLimit,
  getUploadAuthHeaders,
  getUploadSettings,
  getUserId,
  showAdminControls,
} from './apiConfig';

afterEach(() => {
  localStorage.clear();
});

describe('apiConfig', () => {
  it('exports a default API base', () => {
    expect(API_BASE).toBe('/api');
    expect(getTasksPageLimit()).toBe(20);
    expect(showAdminControls()).toBe(false);
  });

  it('reads service tokens into Authorization headers', () => {
    localStorage.setItem('minutes.serviceToken', 'secret-token');
    expect(getAuthHeaders()).toEqual({ Authorization: 'Bearer secret-token' });
  });

  it('falls back to X-User-Id when no token is present', () => {
    localStorage.setItem('minutes.userId', 'user-1');
    expect(getUploadAuthHeaders()).toEqual({ 'X-User-Id': 'user-1' });
  });

  it('creates a user id once and reuses it', () => {
    const first = ensureUserId();
    const second = ensureUserId();
    expect(first.created).toBe(true);
    expect(first.userId).toBeTruthy();
    expect(second).toEqual({ userId: first.userId, created: false });
    expect(getUserId()).toBe(first.userId);
  });

  it('applies stored upload settings to form data', () => {
    localStorage.setItem(
      'minutes.settings',
      JSON.stringify({ language: 'ja', includeActions: false })
    );
    expect(getUploadSettings()).toEqual({ language: 'ja', includeActions: false });
    const formData = new FormData();
    applyUploadSettings(formData);
    expect(formData.get('language')).toBe('ja');
    expect(formData.get('include_actions')).toBe('0');
  });
});

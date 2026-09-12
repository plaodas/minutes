export const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export type UploadSettings = {
  language?: string;
  includeActions?: boolean;
};

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    // localStorage unavailable
    return null;
  }
}

function writeStorage(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    // localStorage unavailable
    return false;
  }
}

export function getApiBase(): string {
  return API_BASE;
}

export function getTasksPageLimit(): number {
  return Number(import.meta.env.VITE_TASKS_PAGE_LIMIT || 20);
}

export function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token =
    readStorage('minutes.serviceToken') ||
    readStorage('service_token') ||
    import.meta.env.VITE_SERVICE_TOKEN;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export function getUserId(): string | null {
  return readStorage('minutes.userId') || readStorage('user_id');
}

export function getUploadAuthHeaders(): Record<string, string> {
  const headers = { ...getAuthHeaders() };
  if (!headers.Authorization) {
    const userId = getUserId();
    if (userId) headers['X-User-Id'] = userId;
  }
  return headers;
}

export function ensureUserId(): { userId: string | null; created: boolean } {
  const existing = getUserId();
  if (existing) return { userId: existing, created: false };

  const generated =
    (typeof crypto !== 'undefined' && crypto.randomUUID?.()) ||
    'id-' + Math.random().toString(36).slice(2, 10);
  if (!writeStorage('minutes.userId', generated)) {
    return { userId: null, created: false };
  }
  return { userId: generated, created: true };
}

export function getUploadSettings(): UploadSettings {
  const raw = readStorage('minutes.settings');
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as UploadSettings;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    // stored settings JSON is invalid
    return {};
  }
}

export function applyUploadSettings(formData: FormData): void {
  const settings = getUploadSettings();
  if (settings.language) formData.append('language', settings.language);
  if (typeof settings.includeActions !== 'undefined') {
    formData.append('include_actions', settings.includeActions ? '1' : '0');
  }
}

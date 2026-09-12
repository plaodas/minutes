import fetchWithRetry from '../lib/fetchWithRetry';
import { parseTaskHistoryResponse, parseTaskListResponse } from '../lib/taskState';
import type { TaskHistoryPreview, TaskListItem } from '../lib/taskState';
import type { TaskStage } from '../lib/taskEvents';

const BASE = import.meta.env.VITE_API_BASE || '/api';

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  try {
    const token =
      localStorage.getItem('minutes.serviceToken') ||
      localStorage.getItem('service_token') ||
      import.meta.env.VITE_SERVICE_TOKEN;
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      return headers;
    }
  } catch (e) {}
  return headers;
}

export async function uploadAudioBg(file: File) {
  const fd = new FormData();
  fd.append('file', file);
  const headers: Record<string, string> = { ...getAuthHeaders() };
  // fallback to X-User-Id for legacy clients/tests
  if (!headers['Authorization']) {
    try {
      const uid = localStorage.getItem('minutes.userId') || localStorage.getItem('user_id');
      if (uid) headers['X-User-Id'] = uid;
    } catch {}
  }
  // include user settings (language, include_actions) if present
  try {
    const raw = localStorage.getItem('minutes.settings');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.language) fd.append('language', s.language);
      if (typeof s?.includeActions !== 'undefined')
        fd.append('include_actions', s.includeActions ? '1' : '0');
    }
  } catch {}
  const res = await fetch(`${BASE}/transcribe-upload-bg`, { method: 'POST', body: fd, headers });
  if (!res.ok) throw new Error('upload failed');
  return res.json(); // { task_id }
}

export function uploadAudioBgWithProgress(file: File, onProgress?: (percent: number) => void) {
  const xhr = new XMLHttpRequest();
  const fd = new FormData();
  fd.append('file', file);
  xhr.open('POST', `${BASE}/transcribe-upload-bg`);

  try {
    const auth = getAuthHeaders();
    if (auth['Authorization']) xhr.setRequestHeader('Authorization', auth['Authorization']);
    else {
      const uid = localStorage.getItem('minutes.userId') || localStorage.getItem('user_id');
      if (uid) xhr.setRequestHeader('X-User-Id', uid);
    }
  } catch {}

  // include user settings (language, include_actions) if present
  try {
    const raw = localStorage.getItem('minutes.settings');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.language) fd.append('language', s.language);
      if (typeof s?.includeActions !== 'undefined')
        fd.append('include_actions', s.includeActions ? '1' : '0');
    }
  } catch {}

  const promise = new Promise<any>((resolve, reject) => {
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const json = JSON.parse(xhr.responseText);
          resolve(json);
        } catch (e) {
          resolve({});
        }
      } else {
        const msg = `upload failed: ${xhr.status} ${xhr.statusText} ${xhr.responseText || ''}`;
        reject(new Error(msg));
      }
    };

    xhr.onerror = () => reject(new Error('upload failed: network error or CORS blocked'));
  });

  if (xhr.upload && onProgress) {
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress(percent);
      }
    };
  }

  // start send after handlers attached
  xhr.send(fd);

  return { xhr, promise };
}

export type BgStatusResponse = {
  task_id: string;
  status: string;
  stage?: TaskStage;
  error?: string | null;
  detail?: string | null;
  message?: string | null;
  progress?: number | null;
};

export async function getBgStatus(taskId: string): Promise<BgStatusResponse> {
  const res = await fetchWithRetry(
    `${BASE}/bg/status/${taskId}`,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: 3, timeoutMs: 10000 }
  );
  if (!res.ok) throw new Error('status fetch failed');
  return res.json() as Promise<BgStatusResponse>;
}

export async function getBgResult(taskId: string) {
  const res = await fetchWithRetry(
    `${BASE}/bg/result/${taskId}`,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: 3, timeoutMs: 10000 }
  );
  if (!res.ok) throw new Error('result fetch failed');
  return res.json();
}

export async function getBgTasks(
  options: {
    limit?: number;
    offset?: number;
    retries?: number;
    timeoutMs?: number;
  } = {}
): Promise<TaskListItem[]> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.offset !== undefined) params.set('offset', String(options.offset));
  const query = params.toString();
  const res = await fetchWithRetry(
    `${BASE}/bg/tasks${query ? `?${query}` : ''}`,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: options.retries ?? 3, timeoutMs: options.timeoutMs ?? 10000 }
  );
  if (!res.ok) throw new Error('task list fetch failed');
  const tasks = parseTaskListResponse(await res.json());
  if (!tasks) throw new Error('invalid task list response');
  return tasks;
}

export async function getBgTaskEvents(taskId: string): Promise<TaskHistoryPreview[]> {
  const res = await fetchWithRetry(
    `${BASE}/bg/tasks/${encodeURIComponent(taskId)}/events`,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: 2, timeoutMs: 10000 }
  );
  if (!res.ok) throw new Error('task events fetch failed');
  const events = parseTaskHistoryResponse(await res.json());
  if (!events) throw new Error('invalid task events response');
  return events;
}

export async function renameBgTask(taskId: string, name: string): Promise<void> {
  const res = await fetchWithRetry(
    `${BASE}/bg/task/${encodeURIComponent(taskId)}/rename`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    },
    { retries: 0, timeoutMs: 10000 }
  );
  if (res.ok) return;
  const body: unknown = await res.json().catch(() => null);
  const message =
    typeof body === 'object' && body !== null && 'error' in body && typeof body.error === 'string'
      ? body.error
      : 'Rename failed';
  throw new Error(message);
}

async function _downloadBlob(url: string) {
  const res = await fetchWithRetry(
    url,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: 2, timeoutMs: 30000 }
  );
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  const blob = await res.blob();
  return { blob, headers: res.headers };
}

export async function fetchTranscriptDownload(taskId: string, format: string = 'txt') {
  const url = `${BASE}/bg/transcript/${taskId}?format=${encodeURIComponent(format)}`;
  return _downloadBlob(url);
}

export async function fetchSummaryDownload(taskId: string, format: string = 'txt') {
  const url = `${BASE}/bg/summary/${taskId}?format=${encodeURIComponent(format)}`;
  return _downloadBlob(url);
}

export async function fetchActionItemsDownload(taskId: string, format: string = 'json') {
  const url = `${BASE}/bg/action-items/${taskId}?format=${encodeURIComponent(format)}`;
  return _downloadBlob(url);
}

export async function deleteTask(taskId: string) {
  const res = await fetch(`${BASE}/bg/delete/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('delete failed');
  return res.json();
}

export async function forceDeleteTask(taskId: string) {
  const res = await fetch(`${BASE}/bg/force-delete/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('force delete failed');
  return res.json();
}

export async function getUserFeatures() {
  const res = await fetch(`${BASE}/auth/features`, { credentials: 'same-origin' });
  if (!res.ok) return { is_admin: false };
  return res.json();
}

export async function adminUploadsCleanupGet(
  opts: { dir?: string; pattern?: string; older_than?: number; limit?: number } = {}
) {
  const params = new URLSearchParams();
  if (opts.dir) params.set('dir', opts.dir);
  if (opts.pattern) params.set('pattern', opts.pattern);
  if (opts.older_than) params.set('older_than', String(opts.older_than));
  if (opts.limit) params.set('limit', String(opts.limit));
  const headers = { ...getAuthHeaders(), 'X-Admin': '1' };
  const res = await fetch(`${BASE}/admin/uploads/cleanup?${params.toString()}`, {
    credentials: 'same-origin',
    headers,
  });
  if (!res.ok) throw new Error('cleanup preview failed');
  return res.json();
}

export async function adminUploadsCleanupPost(payload: {
  dir?: string;
  pattern?: string;
  older_than?: number;
  limit?: number;
}) {
  const headers = { 'Content-Type': 'application/json', ...getAuthHeaders(), 'X-Admin': '1' };
  const res = await fetch(`${BASE}/admin/uploads/cleanup`, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('cleanup run failed');
  return res.json();
}

export async function login(username: string, password: string) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'login failed');
  }
  try {
    return await res.json();
  } catch {
    return res;
  }
}

export async function logout() {
  const res = await fetch(`${BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error('logout failed');
  try {
    return await res.json();
  } catch {
    return res;
  }
}

export async function getBuckets() {
  const res = await fetch(`${BASE}/buckets`, {
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('failed to fetch buckets');
  return res.json();
}

export async function createBucket(name: string) {
  const res = await fetch(`${BASE}/buckets`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('failed to create bucket');
  return res.json();
}

export async function listServiceTokens() {
  const res = await fetch(`${BASE}/service-tokens`, {
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('failed to fetch service tokens');
  return res.json();
}

export async function createServiceToken(name?: string, user_id?: string) {
  const res = await fetch(`${BASE}/service-tokens`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ name, user_id }),
  });
  if (!res.ok) throw new Error('failed to create service token');
  return res.json();
}

export async function revokeServiceToken(id: string) {
  const res = await fetch(`${BASE}/service-tokens/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('failed to revoke token');
  return res.json();
}

export async function undeleteTask(taskId: string) {
  const res = await fetch(`${BASE}/bg/undelete/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('undelete failed');
  return res.json();
}

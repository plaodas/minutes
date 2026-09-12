import {
  API_BASE,
  applyUploadSettings,
  getAuthHeaders,
  getUploadAuthHeaders,
} from '../lib/apiConfig';
import fetchWithRetry from '../lib/fetchWithRetry';
import { parseTaskHistoryResponse, parseTaskListResponse } from '../lib/taskState';
import type { TaskHistoryPreview, TaskListItem } from '../lib/taskState';

import type {
  AuthFeaturesResponse,
  AuthLoginResponse,
  AuthLogoutResponse,
  CreateTaskResponse,
  ResultSuccess,
  RevokedResponse,
  ServiceTokenCreatedResponse,
  ServiceTokenListResponse,
  StatusResponse,
  TaskDeletedResponse,
  TaskUndeletedResponse,
  UploadCleanupDeleteResponse,
  UploadCleanupListResponse,
  UserBucketListResponse,
  UserBucketResponse,
} from './types';

export type UploadTaskResponse = CreateTaskResponse & {
  taskId?: string;
  id?: string;
};

export async function uploadAudioBg(file: File): Promise<UploadTaskResponse> {
  const fd = new FormData();
  fd.append('file', file);
  applyUploadSettings(fd);
  const res = await fetch(`${API_BASE}/transcribe-upload-bg`, {
    method: 'POST',
    body: fd,
    headers: getUploadAuthHeaders(),
  });
  if (!res.ok) throw new Error('upload failed');
  return res.json() as Promise<UploadTaskResponse>;
}

export function uploadAudioBgWithProgress(file: File, onProgress?: (percent: number) => void) {
  const xhr = new XMLHttpRequest();
  const fd = new FormData();
  fd.append('file', file);
  applyUploadSettings(fd);
  xhr.open('POST', `${API_BASE}/transcribe-upload-bg`);

  for (const [name, value] of Object.entries(getUploadAuthHeaders())) {
    xhr.setRequestHeader(name, value);
  }

  const promise = new Promise<UploadTaskResponse>((resolve, reject) => {
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadTaskResponse);
        } catch {
          // upload response was not JSON
          resolve({ task_id: '' });
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

export type BgStatusResponse = StatusResponse;

export async function getBgStatus(taskId: string): Promise<BgStatusResponse> {
  const res = await fetchWithRetry(
    `${API_BASE}/bg/status/${taskId}`,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: 3, timeoutMs: 10000 }
  );
  if (!res.ok) throw new Error('status fetch failed');
  return res.json() as Promise<BgStatusResponse>;
}

export async function getBgResult(taskId: string): Promise<ResultSuccess> {
  const res = await fetchWithRetry(
    `${API_BASE}/bg/result/${taskId}`,
    { credentials: 'same-origin', headers: getAuthHeaders() },
    { retries: 3, timeoutMs: 10000 }
  );
  if (!res.ok) throw new Error('result fetch failed');
  return res.json() as Promise<ResultSuccess>;
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
    `${API_BASE}/bg/tasks${query ? `?${query}` : ''}`,
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
    `${API_BASE}/bg/tasks/${encodeURIComponent(taskId)}/events`,
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
    `${API_BASE}/bg/task/${encodeURIComponent(taskId)}/rename`,
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

async function _downloadBlob(url: string): Promise<{ blob: Blob; headers: Headers }> {
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
  const url = `${API_BASE}/bg/transcript/${taskId}?format=${encodeURIComponent(format)}`;
  return _downloadBlob(url);
}

export async function fetchSummaryDownload(taskId: string, format: string = 'txt') {
  const url = `${API_BASE}/bg/summary/${taskId}?format=${encodeURIComponent(format)}`;
  return _downloadBlob(url);
}

export async function fetchActionItemsDownload(taskId: string, format: string = 'json') {
  const url = `${API_BASE}/bg/action-items/${taskId}?format=${encodeURIComponent(format)}`;
  return _downloadBlob(url);
}

export async function deleteTask(taskId: string): Promise<TaskDeletedResponse> {
  const res = await fetch(`${API_BASE}/bg/delete/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('delete failed');
  return res.json();
}

export async function forceDeleteTask(taskId: string): Promise<TaskDeletedResponse> {
  const res = await fetch(`${API_BASE}/bg/force-delete/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('force delete failed');
  return res.json();
}

export async function getUserFeatures(): Promise<AuthFeaturesResponse> {
  const res = await fetch(`${API_BASE}/auth/features`, { credentials: 'same-origin' });
  if (!res.ok) return { is_admin: false, authenticated: false };
  return res.json() as Promise<AuthFeaturesResponse>;
}

export async function adminUploadsCleanupGet(
  opts: { dir?: string; pattern?: string; older_than?: number; limit?: number } = {}
): Promise<UploadCleanupListResponse> {
  const params = new URLSearchParams();
  if (opts.dir) params.set('dir', opts.dir);
  if (opts.pattern) params.set('pattern', opts.pattern);
  if (opts.older_than) params.set('older_than', String(opts.older_than));
  if (opts.limit) params.set('limit', String(opts.limit));
  const headers = { ...getAuthHeaders(), 'X-Admin': '1' };
  const res = await fetch(`${API_BASE}/admin/uploads/cleanup?${params.toString()}`, {
    credentials: 'same-origin',
    headers,
  });
  if (!res.ok) throw new Error('cleanup preview failed');
  return res.json() as Promise<UploadCleanupListResponse>;
}

export async function adminUploadsCleanupPost(payload: {
  dir?: string;
  pattern?: string;
  older_than?: number;
  limit?: number;
}): Promise<UploadCleanupDeleteResponse> {
  const headers = { 'Content-Type': 'application/json', ...getAuthHeaders(), 'X-Admin': '1' };
  const res = await fetch(`${API_BASE}/admin/uploads/cleanup`, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('cleanup run failed');
  return res.json() as Promise<UploadCleanupDeleteResponse>;
}

export async function login(
  username: string,
  password: string
): Promise<AuthLoginResponse | Response> {
  const res = await fetch(`${API_BASE}/auth/login`, {
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
    // login body was not JSON
    return res;
  }
}

export async function logout(): Promise<AuthLogoutResponse | Response> {
  const res = await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error('logout failed');
  try {
    return (await res.json()) as AuthLogoutResponse;
  } catch {
    // logout body was not JSON
    return res;
  }
}

export async function getBuckets(): Promise<UserBucketListResponse> {
  const res = await fetch(`${API_BASE}/buckets`, {
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('failed to fetch buckets');
  return res.json() as Promise<UserBucketListResponse>;
}

export async function createBucket(name: string): Promise<UserBucketResponse> {
  const res = await fetch(`${API_BASE}/buckets`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('failed to create bucket');
  return res.json() as Promise<UserBucketResponse>;
}

export async function listServiceTokens(): Promise<ServiceTokenListResponse> {
  const res = await fetch(`${API_BASE}/service-tokens`, {
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('failed to fetch service tokens');
  return res.json() as Promise<ServiceTokenListResponse>;
}

export async function createServiceToken(
  name?: string,
  user_id?: string
): Promise<ServiceTokenCreatedResponse> {
  const res = await fetch(`${API_BASE}/service-tokens`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ name, user_id }),
  });
  if (!res.ok) throw new Error('failed to create service token');
  return res.json() as Promise<ServiceTokenCreatedResponse>;
}

export async function revokeServiceToken(id: string): Promise<RevokedResponse> {
  const res = await fetch(`${API_BASE}/service-tokens/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('failed to revoke token');
  return res.json() as Promise<RevokedResponse>;
}

export async function undeleteTask(taskId: string): Promise<TaskUndeletedResponse> {
  const res = await fetch(`${API_BASE}/bg/undelete/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('undelete failed');
  return res.json();
}

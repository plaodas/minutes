import React, { useEffect, useState } from 'react';

import { listAuditEvents } from '../api/client';
import type { AuditEventItem } from '../api/types';
import { errorMessage } from '../lib/errorMessage';

import { useToast } from './ToastProvider';

const ACTIONS = [
  'auth.login.success',
  'auth.login.failure',
  'service_token.create',
  'service_token.revoke',
  'external_user.provision',
  'task.delete',
  'task.undelete',
  'task.force_delete',
  'task.hard_delete',
  'upload.cleanup',
  'bucket.delete',
];

function actorLine(event: AuditEventItem): string {
  const parts = [`操作者: ${event.actor_kind}`];
  if (event.actor_user_id) parts.push(`ユーザー: ${event.actor_user_id}`);
  if (event.actor_token_id) parts.push(`トークン: ${event.actor_token_id}`);
  return parts.join(' · ');
}

type AuditFilters = { action?: string; target_type?: string; target_id?: string };

export default function AuditEventsAdmin() {
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [action, setAction] = useState('');
  const [targetType, setTargetType] = useState('');
  const [targetId, setTargetId] = useState('');
  const [applied, setApplied] = useState<AuditFilters>({});
  const { addToast } = useToast();

  const load = async (filters: AuditFilters, before?: AuditEventItem) => {
    if (before) setLoadingMore(true);
    else setLoading(true);
    try {
      const data = await listAuditEvents(
        before?.created_at
          ? {
              ...filters,
              before_created_at: before.created_at,
              before_id: before.id,
            }
          : filters
      );
      const incoming = data.events || [];
      setHasMore(data.has_more === true);
      if (before) {
        setEvents((current) => {
          const seen = new Set(current.map((event) => event.id));
          return [...current, ...incoming.filter((event) => !seen.has(event.id))];
        });
      } else {
        setEvents(incoming);
      }
    } catch (e: unknown) {
      addToast(errorMessage(e, '監査イベントの読み込みに失敗しました'), { level: 'error' });
    } finally {
      if (before) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    void load({});
  }, []);

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    const filters = {
      action: action || undefined,
      target_type: targetType || undefined,
      target_id: targetId || undefined,
    };
    setApplied(filters);
    void load(filters);
  };

  const showOlder = () => {
    const last = events[events.length - 1];
    if (!last?.created_at) return;
    void load(applied, last);
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">監査イベント</h2>
        <p className="text-sm text-[var(--muted)]">
          アクセスと保存データの最近の変更です。新しい順です。
        </p>
      </div>

      <form onSubmit={handleFilter} className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <select
          aria-label="操作"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded border px-2 py-1"
        >
          <option value="">すべての操作</option>
          {ACTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <input
          aria-label="対象の種類"
          value={targetType}
          onChange={(e) => setTargetType(e.target.value)}
          placeholder="対象の種類"
          className="rounded border px-2 py-1"
        />
        <input
          aria-label="対象 ID"
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          placeholder="対象 ID"
          className="min-w-0 flex-1 rounded border px-2 py-1"
        />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" type="submit">
          表示
        </button>
      </form>

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">読み込み中…</div>
        ) : events.length === 0 ? (
          <div className="text-sm text-[var(--muted)]">監査イベントはありません。</div>
        ) : (
          <ul className="space-y-2">
            {events.map((event) => (
              <li key={event.id} className="rounded border p-2">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <div className="text-xs text-[var(--muted)]">{event.created_at || '—'}</div>
                  <div className="font-medium">{event.action}</div>
                </div>
                <div className="break-all text-xs text-[var(--muted)]">{actorLine(event)}</div>
                <div className="break-all text-sm">
                  {event.target_type}: {event.target_id}
                </div>
                {event.detail && (
                  <pre className="mt-1 whitespace-pre-wrap break-all text-xs text-[var(--muted)]">
                    {JSON.stringify(event.detail)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
        {hasMore && events.length > 0 && events[events.length - 1]?.created_at && (
          <button
            type="button"
            className="mt-3 rounded border px-3 py-1 text-sm"
            disabled={loading || loadingMore}
            onClick={showOlder}
          >
            {loadingMore ? '読み込み中…' : 'さらに古いものを表示'}
          </button>
        )}
      </div>
    </div>
  );
}

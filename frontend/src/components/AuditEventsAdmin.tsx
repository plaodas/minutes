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
  const parts = [`actor: ${event.actor_kind}`];
  if (event.actor_user_id) parts.push(`user: ${event.actor_user_id}`);
  if (event.actor_token_id) parts.push(`token: ${event.actor_token_id}`);
  return parts.join(' · ');
}

export default function AuditEventsAdmin() {
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState('');
  const [targetType, setTargetType] = useState('');
  const [targetId, setTargetId] = useState('');
  const { addToast } = useToast();

  const load = async (filters: { action?: string; target_type?: string; target_id?: string }) => {
    setLoading(true);
    try {
      const data = await listAuditEvents(filters);
      setEvents(data.events || []);
    } catch (e: unknown) {
      addToast(errorMessage(e, 'failed to load audit events'), { level: 'error' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load({});
  }, []);

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    void load({
      action: action || undefined,
      target_type: targetType || undefined,
      target_id: targetId || undefined,
    });
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Audit events</h2>
        <p className="text-sm text-[var(--muted)]">
          Recent changes to access and stored data, newest first.
        </p>
      </div>

      <form onSubmit={handleFilter} className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <select
          aria-label="action"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded border px-2 py-1"
        >
          <option value="">all actions</option>
          {ACTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <input
          aria-label="target type"
          value={targetType}
          onChange={(e) => setTargetType(e.target.value)}
          placeholder="target type"
          className="rounded border px-2 py-1"
        />
        <input
          aria-label="target id"
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          placeholder="target id"
          className="min-w-0 flex-1 rounded border px-2 py-1"
        />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" type="submit">
          Show
        </button>
      </form>

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">Loading…</div>
        ) : events.length === 0 ? (
          <div className="text-sm text-[var(--muted)]">No audit events.</div>
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
      </div>
    </div>
  );
}

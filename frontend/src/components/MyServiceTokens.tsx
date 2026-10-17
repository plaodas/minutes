import React, { useEffect, useState } from 'react';

import { createMyServiceToken, listMyServiceTokens, revokeMyServiceToken } from '../api/client';
import type { ServiceTokenItem } from '../api/types';
import { errorMessage } from '../lib/errorMessage';

import ConfirmModal from './ConfirmModal';
import { useToast } from './ToastProvider';

export default function MyServiceTokens() {
  const [tokens, setTokens] = useState<ServiceTokenItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const { addToast } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState('');
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await listMyServiceTokens();
      setTokens(data.tokens || []);
    } catch (e: unknown) {
      addToast(errorMessage(e, 'failed to load tokens'), { level: 'error' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data = await createMyServiceToken(name || undefined);
      addToast('Token created — copy it now (shown once)', { level: 'success' });
      try {
        window.prompt('Service token (copy and store securely):', data.token);
      } catch {
        // window.prompt can throw if the browser blocks it
      }
      setName('');
      await load();
    } catch (e: unknown) {
      addToast(errorMessage(e, 'create failed'), { level: 'error' });
    }
  };

  const handleRevoke = async (id: string) => {
    setConfirmMessage('Revoke this token?');
    setConfirmAction(() => async () => {
      setConfirmOpen(false);
      try {
        await revokeMyServiceToken(id);
        addToast('Token revoked', { level: 'success' });
        await load();
      } catch (e: unknown) {
        addToast(errorMessage(e, 'revoke failed'), { level: 'error' });
      }
    });
    setConfirmOpen(true);
  };

  return (
    <div className="mt-8">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Service tokens</h2>
        <p className="text-sm text-[var(--muted)]">
          Create a token for this account. Copy it when it appears; it is shown once.
        </p>
      </div>

      <form onSubmit={handleCreate} className="mb-4 flex flex-col gap-2 sm:flex-row">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="token name (optional)"
          aria-label="token name"
          className="rounded border px-2 py-1"
        />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" type="submit">
          Create token
        </button>
      </form>

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">Loading…</div>
        ) : tokens.length === 0 ? (
          <div className="text-sm text-[var(--muted)]">No service tokens.</div>
        ) : (
          <ul className="space-y-2">
            {tokens.map((token) => (
              <li
                key={token.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border p-2"
              >
                <div
                  className={`min-w-0 break-all font-medium ${token.revoked ? 'text-[var(--muted)]' : ''}`}
                >
                  {token.name || token.id}
                  {token.revoked && (
                    <span className="ml-2 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700">
                      Revoked
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRevoke(token.id)}
                  disabled={token.revoked}
                  className="rounded bg-red-600 px-2 py-1 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmModal
        open={confirmOpen}
        title="Confirm"
        message={confirmMessage}
        confirmLabel="Revoke"
        cancelLabel="Cancel"
        onConfirm={() => {
          if (confirmAction) confirmAction();
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

import React, { useEffect, useState } from 'react';

import { createMyServiceToken, listMyServiceTokens, revokeMyServiceToken } from '../api/client';
import type { ServiceTokenItem } from '../api/types';
import { errorMessage } from '../lib/errorMessage';

import ConfirmModal from './ConfirmModal';
import CreatedServiceToken from './CreatedServiceToken';
import { useToast } from './ToastProvider';

export default function MyServiceTokens() {
  const [tokens, setTokens] = useState<ServiceTokenItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [createdToken, setCreatedToken] = useState<string | null>(null);
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
      addToast(errorMessage(e, 'トークンの読み込みに失敗しました'), { level: 'error' });
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
      setCreatedToken(data.token);
      addToast('トークンを作成しました', { level: 'success' });
      setName('');
      await load();
    } catch (e: unknown) {
      addToast(errorMessage(e, '作成に失敗しました'), { level: 'error' });
    }
  };

  const handleRevoke = async (id: string) => {
    setConfirmMessage('このトークンを失効しますか？');
    setConfirmAction(() => async () => {
      setConfirmOpen(false);
      try {
        await revokeMyServiceToken(id);
        addToast('トークンを失効しました', { level: 'success' });
        await load();
      } catch (e: unknown) {
        addToast(errorMessage(e, '失効に失敗しました'), { level: 'error' });
      }
    });
    setConfirmOpen(true);
  };

  return (
    <div className="mt-8">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">サービストークン</h2>
        <p className="text-sm text-[var(--muted)]">
          このアカウント用のトークンを作成します。作成すると、この画面に一度だけ表示されます。
        </p>
      </div>

      {createdToken && (
        <CreatedServiceToken token={createdToken} onClose={() => setCreatedToken(null)} />
      )}

      <form onSubmit={handleCreate} className="mb-4 flex flex-col gap-2 sm:flex-row">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="トークン名（任意）"
          aria-label="トークン名"
          className="rounded border px-2 py-1"
        />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" type="submit">
          トークンを作成
        </button>
      </form>

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">読み込み中…</div>
        ) : tokens.length === 0 ? (
          <div className="text-sm text-[var(--muted)]">サービストークンはありません。</div>
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
                      失効済み
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRevoke(token.id)}
                  disabled={token.revoked}
                  className="rounded bg-red-600 px-2 py-1 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  失効
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmModal
        open={confirmOpen}
        title="確認"
        message={confirmMessage}
        confirmLabel="失効"
        cancelLabel="キャンセル"
        onConfirm={() => {
          if (confirmAction) confirmAction();
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

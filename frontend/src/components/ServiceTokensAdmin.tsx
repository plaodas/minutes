import React, { useEffect, useState } from 'react';

import {
  listServiceTokens,
  listUsers,
  createServiceToken,
  revokeServiceToken,
} from '../api/client';
import type { ServiceTokenItem, UserListResponse } from '../api/types';
import { errorMessage } from '../lib/errorMessage';

import ConfirmModal from './ConfirmModal';
import CreatedServiceToken from './CreatedServiceToken';
import { useToast } from './ToastProvider';

function userLine(token: ServiceTokenItem): string {
  if (token.username && token.user_id) return `${token.username} · ${token.user_id}`;
  if (token.user_id) return token.user_id;
  return '—';
}

export default function ServiceTokensAdmin() {
  const [tokens, setTokens] = useState<ServiceTokenItem[]>([]);
  const [users, setUsers] = useState<UserListResponse['users']>([]);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [userId, setUserId] = useState('');
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const { addToast } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState('');
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [tokenData, userData] = await Promise.all([listServiceTokens(), listUsers()]);
      setTokens(tokenData.tokens || []);
      setUsers(userData.users || []);
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
    if (!userId) return;
    try {
      const data = await createServiceToken(name || undefined, userId);
      setCreatedToken(data.token);
      addToast('トークンを作成しました', { level: 'success' });
      setName('');
      setUserId('');
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
        await revokeServiceToken(id);
        addToast('トークンを失効しました', { level: 'success' });
        await load();
      } catch (e: unknown) {
        addToast(errorMessage(e, '失効に失敗しました'), { level: 'error' });
      }
    });
    setConfirmOpen(true);
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">サービストークン</h2>
        <p className="text-sm text-[var(--muted)]">
          プログラムから使うサービストークンを作成し、失効します。
        </p>
      </div>

      {createdToken && (
        <CreatedServiceToken token={createdToken} onClose={() => setCreatedToken(null)} />
      )}

      <form onSubmit={handleCreate} className="mb-4 flex flex-col sm:flex-row gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="トークン名（任意）"
          className="rounded border px-2 py-1"
        />
        <select
          aria-label="ユーザー"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="rounded border px-2 py-1"
        >
          <option value="">ユーザーを選択</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.username}
            </option>
          ))}
        </select>
        <button
          className="rounded bg-[var(--accent)] px-3 py-1 text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          type="submit"
          disabled={!userId}
        >
          トークンを作成
        </button>
      </form>

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">読み込み中…</div>
        ) : (
          <ul className="space-y-2">
            {tokens.map((t) => (
              <li
                key={t.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border p-2"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div
                      className={`break-all font-medium ${t.revoked ? 'text-[var(--muted)]' : ''}`}
                    >
                      {t.name || t.id}
                    </div>
                    {t.revoked && (
                      <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700">
                        失効済み
                      </span>
                    )}
                  </div>
                  <div className="break-all text-xs text-[var(--muted)]">
                    ユーザー: {userLine(t)}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() => {
                      try {
                        window.prompt('トークン ID:', t.id);
                      } catch {
                        // window.prompt can throw if the browser blocks it
                      }
                    }}
                    className="rounded bg-slate-100 px-2 py-1 text-sm"
                  >
                    ID を表示
                  </button>
                  <button
                    onClick={() => handleRevoke(t.id)}
                    disabled={t.revoked}
                    className="rounded bg-red-600 px-2 py-1 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    失効
                  </button>
                </div>
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

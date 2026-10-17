import React, { useState } from 'react';

import { login } from '../api/client';
import { errorMessage } from '../lib/errorMessage';

import { useToast } from './ToastProvider';

export default function LoginForm() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { addToast } = useToast();

  const doLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(username, password);
      addToast('ログインしました', { level: 'success' });
      window.dispatchEvent(new CustomEvent('auth-changed'));
    } catch (err: unknown) {
      addToast(errorMessage(err, 'ログインに失敗しました'), { level: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-sm font-medium text-[var(--accent)]">Minutes</p>
      <h1 className="mt-1 text-2xl font-semibold">ログイン</h1>
      <p className="mt-2 text-sm text-[var(--muted)]">
        ローカルのデモアカウントで、音声をアップロードして議事録を確認します。
      </p>
      <form onSubmit={doLogin} className="mt-5 flex flex-col gap-2">
        <input
          aria-label="ユーザー名"
          placeholder="ユーザー名"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full rounded border px-3 py-2 text-sm"
        />
        <input
          aria-label="パスワード"
          placeholder="パスワード"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border px-3 py-2 text-sm"
        />
        <div className="mt-2 flex items-center justify-end">
          <button
            type="submit"
            disabled={loading}
            className="rounded bg-[var(--accent)] px-3 py-2 text-sm text-white"
          >
            ログイン
          </button>
        </div>
      </form>
    </div>
  );
}

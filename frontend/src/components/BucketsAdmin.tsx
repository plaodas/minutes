import React, { useEffect, useState } from 'react';

import {
  getBuckets,
  createBucket,
  adminUploadsCleanupGet,
  adminUploadsCleanupPost,
} from '../api/client';
import type {
  UploadCleanupCandidate,
  UploadCleanupDeleteResponse,
  UserBucketListItem,
} from '../api/types';
import { dispatchAppToast } from '../lib/appEvents';
import { errorMessage } from '../lib/errorMessage';

import ConfirmModal from './ConfirmModal';

export default function BucketsAdmin() {
  const [buckets, setBuckets] = useState<UserBucketListItem[]>([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [uploadsDir, setUploadsDir] = useState('');
  const [uploadsPattern, setUploadsPattern] = useState('');
  const [olderThan, setOlderThan] = useState<number>(0);
  const [limit, setLimit] = useState<number>(100);
  const [preview, setPreview] = useState<UploadCleanupCandidate[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [runResult, setRunResult] = useState<UploadCleanupDeleteResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState('');
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await getBuckets();
      setBuckets(data.buckets || []);
    } catch (e: unknown) {
      setError(errorMessage(e, '失敗しました'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await createBucket(name);
      setName('');
      await load();
    } catch (e: unknown) {
      setError(errorMessage(e, '作成に失敗しました'));
    }
  };

  const handlePreview = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError(null);
    setPreview(null);
    setRunResult(null);
    setPreviewLoading(true);
    try {
      const res = await adminUploadsCleanupGet({
        dir: uploadsDir || undefined,
        pattern: uploadsPattern,
        older_than: olderThan || 0,
        limit,
      });
      setPreview(res.candidates || []);
    } catch (err: unknown) {
      const msg = errorMessage(err, 'プレビューに失敗しました');
      setError(msg);
      dispatchAppToast({ type: 'error', message: msg });
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleRun = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError(null);
    setConfirmMessage('一致するアップロードファイルを削除しますか？元に戻せません。');
    setConfirmAction(() => async () => {
      setConfirmOpen(false);
      setRunLoading(true);
      setRunResult(null);
      try {
        const res = await adminUploadsCleanupPost({
          dir: uploadsDir || undefined,
          pattern: uploadsPattern,
          older_than: olderThan || 0,
          limit,
        });
        setRunResult(res);
        setPreview(null);
        dispatchAppToast({
          type: 'success',
          message: `${res.count || 0} 件のファイルを削除しました`,
        });
      } catch (err: unknown) {
        const msg = errorMessage(err, 'クリーンアップに失敗しました');
        setError(msg);
        dispatchAppToast({ type: 'error', message: msg });
      } finally {
        setRunLoading(false);
      }
    });
    setConfirmOpen(true);
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">管理ツール</h2>
        <p className="text-sm text-[var(--muted)]">
          バケット、サービストークン、管理機能を扱います。
        </p>
      </div>

      <div className="mb-4 rounded border p-3">
        <h3 className="font-medium">アップロードの整理</h3>
        <p className="text-xs text-[var(--muted)]">
          共有アップロードディレクトリのファイルを確認して削除します。管理者のみ。
        </p>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-4">
          <input
            className="rounded border px-2 py-1"
            placeholder="ディレクトリ（任意）"
            value={uploadsDir}
            onChange={(e) => setUploadsDir(e.target.value)}
          />
          <input
            className="rounded border px-2 py-1"
            placeholder="パターンの接頭辞"
            value={uploadsPattern}
            onChange={(e) => setUploadsPattern(e.target.value)}
          />
          <input
            className="rounded border px-2 py-1"
            placeholder="経過秒数"
            value={String(olderThan)}
            onChange={(e) => setOlderThan(Number(e.target.value || 0))}
          />
          <input
            className="rounded border px-2 py-1"
            placeholder="上限"
            value={String(limit)}
            onChange={(e) => setLimit(Number(e.target.value || 100))}
          />
        </div>
        <div className="mt-3 flex gap-2">
          <button
            className="rounded border px-3 py-1"
            onClick={handlePreview}
            disabled={previewLoading}
          >
            {previewLoading ? 'プレビュー中…' : 'プレビュー'}
          </button>
          <button
            className="rounded bg-[var(--accent)] px-3 py-1 text-white"
            onClick={handleRun}
            disabled={runLoading}
          >
            {runLoading ? '実行中…' : '整理を実行'}
          </button>
        </div>

        {preview && (
          <div className="mt-3">
            <div className="text-xs text-[var(--muted)]">候補 ({preview.length})</div>
            <ul className="mt-2 max-h-40 overflow-auto text-sm list-disc list-inside">
              {preview.map((c, i) => (
                <li key={c.path || i}>{c.path || c.name}</li>
              ))}
            </ul>
          </div>
        )}

        {runResult && (
          <div className="mt-3 text-sm">
            <div className="text-xs text-[var(--muted)]">削除: {runResult.count || 0}</div>
            {runResult.errors && runResult.errors.length > 0 && (
              <div className="mt-2 text-xs text-red-600">
                エラー: {runResult.errors.map((err) => `${err.path}: ${err.error}`).join('; ')}
              </div>
            )}
          </div>
        )}
      </div>

      <form onSubmit={handleCreate} className="mb-4 flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="バケット名"
          className="rounded border px-2 py-1"
        />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" disabled={!name}>
          作成
        </button>
      </form>

      {error && <div className="mb-2 text-sm text-red-600">{error}</div>}

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">読み込み中…</div>
        ) : (
          <ul className="space-y-2">
            {buckets.map((b) => (
              <li key={b.id} className="rounded border p-2">
                <div className="font-medium">{b.name}</div>
                <div className="text-xs text-[var(--muted)]">所有者: {b.owner_id || '—'}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmModal
        open={confirmOpen}
        title="確認"
        message={confirmMessage}
        confirmLabel="削除"
        cancelLabel="キャンセル"
        onConfirm={() => {
          if (confirmAction) confirmAction();
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

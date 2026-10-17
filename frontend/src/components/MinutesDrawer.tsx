import React, { useEffect, useState } from 'react';

import {
  fetchMinutesDocx,
  fetchTranscriptDownload,
  fetchSummaryDownload,
  fetchActionItemsDownload,
  deleteTask,
  undeleteTask,
  forceDeleteTask,
  getBgResult,
  getBgTasks,
  renameBgTask,
} from '../api/client';
import { API_BASE, getAuthHeaders, showAdminControls } from '../lib/apiConfig';
import { dispatchTaskChanged } from '../lib/appEvents';
import startDownload from '../lib/download';
import { errorMessage } from '../lib/errorMessage';

import MarkdownBody from './MarkdownBody';
import SpeakerEditor from './SpeakerEditor';
import Toast from './Toast';
import ConfirmDialog from './ConfirmDialog';
import { useToast } from './ToastProvider';

const STILL_PROCESSING = '議事録はまだ処理中です';
const MISSING_MINUTES_FILE = 'no output file available';

async function missingMinutesFile(error: unknown): Promise<boolean> {
  if (!(error instanceof Response) || error.status !== 404) return false;
  const body = await error
    .clone()
    .json()
    .catch(() => ({}));
  return body?.error === MISSING_MINUTES_FILE;
}

export function MinutesDrawer({ taskId, onClose }: { taskId: string | null; onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [transcriptOnly, setTranscriptOnly] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [taskName, setTaskName] = useState<string | null>(null);
  const [segments, setSegments] = useState<unknown[]>([]);
  const toast = useToast();
  const adminUiEnabled = showAdminControls();
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    if (!adminUiEnabled) return;
    let mounted = true;
    (async () => {
      try {
        const resp = await import('../api/client').then((m) => m.getUserFeatures());
        if (mounted && resp && resp.is_admin) setIsAdmin(true);
      } catch {
        // admin features are optional for the drawer
      }
    })();
    return () => {
      mounted = false;
    };
  }, [adminUiEnabled]);
  useEffect(() => {
    if (!taskId) return;
    // allow mount to complete before showing for CSS transition
    const id = setTimeout(() => setIsVisible(true), 10);
    return () => clearTimeout(id);
  }, [taskId]);

  // fetch task name for header display
  useEffect(() => {
    if (!taskId) {
      setTaskName(null);
      return;
    }
    (async () => {
      try {
        const tasks = await getBgTasks({ retries: 1, timeoutMs: 8000 });
        const found = tasks.find((task) => task.id === taskId);
        if (found) {
          setTaskName(found.name || null);
          const result = found.result;
          if (result && typeof result === 'object' && 'segments' in result) {
            setSegments(Array.isArray(result.segments) ? result.segments : []);
          }
        }
        const full = await getBgResult(taskId);
        const nested = full.result;
        if (nested && typeof nested === 'object' && Array.isArray(nested.segments)) {
          setSegments(nested.segments);
        }
      } catch {
        // task name is optional for the drawer header
      }
    })();
  }, [taskId]);
  useEffect(() => {
    if (!taskId) return;
    const fetchMinutes = async () => {
      setLoading(true);
      setError(null);
      setText(null);
      setTranscriptOnly(false);
      setSummary(null);
      const fetchWithRetry = (await import('../lib/fetchWithRetry')).default;
      try {
        const res = await fetchWithRetry(
          `${API_BASE}/bg/minutes/${taskId}`,
          { credentials: 'same-origin', headers: getAuthHeaders() },
          { retries: 2, timeoutMs: 10000 }
        );
        if (res.status === 202) {
          setError(STILL_PROCESSING);
          return;
        }
        if (!res.ok) {
          const j = await res.json().catch(() => ({}));
          setError(j?.error || `議事録の読み込みに失敗しました (${res.status})`);
          return;
        }
        const txt = await res.text();
        setTranscriptOnly(false);
        setText(txt);
        // try to fetch a short summary separately (prefer backend /bg/summary)
        (async () => {
          try {
            const sres = await fetchWithRetry(
              `${API_BASE}/bg/summary/${taskId}?format=txt`,
              { credentials: 'same-origin', headers: getAuthHeaders() },
              { retries: 1, timeoutMs: 8000 }
            );
            if (sres.ok) {
              const stext = await sres.text();
              if (stext) setSummary(stext);
            }
          } catch {
            // ignore; summary is optional
          }
        })();
      } catch (e: unknown) {
        if (await missingMinutesFile(e)) {
          try {
            const transcriptResponse = await fetchWithRetry(
              `${API_BASE}/bg/transcript/${taskId}`,
              { credentials: 'same-origin', headers: getAuthHeaders() },
              { retries: 2, timeoutMs: 10000 }
            );
            setText(await transcriptResponse.text());
            setTranscriptOnly(true);
            return;
          } catch (transcriptError: unknown) {
            setError(errorMessage(transcriptError, '取得に失敗しました'));
            return;
          }
        }
        setError(errorMessage(e, '取得に失敗しました'));
      } finally {
        setLoading(false);
      }
    };
    fetchMinutes();
  }, [taskId]);

  const handleClose = () => {
    setIsVisible(false);
    // wait for animation to finish then call onClose
    setTimeout(() => onClose(), 260);
  };

  const handleCopyLink = async () => {
    if (!taskId) {
      toast.addToast('タスク ID がありません', { level: 'error' });
      return;
    }
    const url = `${location.origin}${location.pathname}#minutes=${taskId}`;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      toast.addToast('リンクをクリップボードにコピーしました', { level: 'success' });
      setLiveMessage('リンクをコピーしました');
      setTimeout(() => setLiveMessage(null), 2000);
    } catch {
      toast.addToast('コピーに失敗しました', { level: 'error' });
    }
  };

  const handleCopyTaskId = async () => {
    if (!taskId) {
      toast.addToast('タスク ID がありません', { level: 'error' });
      return;
    }
    try {
      const idOnly = taskId;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(idOnly);
      } else {
        const ta = document.createElement('textarea');
        ta.value = idOnly;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      toast.addToast('タスク ID をクリップボードにコピーしました', { level: 'success' });
      setLiveMessage('タスク ID をコピーしました');
      setTimeout(() => setLiveMessage(null), 2000);
    } catch {
      toast.addToast('コピーに失敗しました', { level: 'error' });
    }
  };

  const [confirmOpen, setConfirmOpen] = useState(false);
  const handleDeleteConfirmed = async () => {
    if (!taskId) return;
    try {
      // If minutes are still processing (no text and error indicating processing), call force-delete
      const isProcessing = error === STILL_PROCESSING && !text;
      if (isProcessing) {
        await forceDeleteTask(taskId);
        toast.addToast('強制削除しました', { level: 'success' });
      } else {
        await deleteTask(taskId);
        toast.addToast('削除しました', {
          level: 'success',
          actionLabel: '元に戻す',
          action: async () => {
            try {
              await undeleteTask(taskId);
              toast.addToast('復元しました', { level: 'success' });
            } catch {
              // restore is best-effort from the undo toast
              toast.addToast('復元に失敗しました', { level: 'error' });
            }
          },
        });
      }
      // optionally close drawer
      setIsVisible(false);
      setTimeout(() => onClose(), 260);
      dispatchTaskChanged(taskId, 'deleted');
    } catch {
      toast.addToast('削除に失敗しました', { level: 'error' });
    }
  };

  const handleDelete = () => {
    setConfirmOpen(true);
  };

  if (!taskId) return null;
  const overlayClass = `fixed inset-0 z-40 flex p-6 transition-colors duration-200 ${isVisible ? 'bg-black/40 pointer-events-auto' : 'bg-black/0 pointer-events-none'}`;

  // The drawer behaves as a right-side panel on md+ and a bottom sheet on small screens.
  const drawerBase =
    'relative max-h-[90vh] w-full max-w-2xl overflow-auto bg-white p-6 transform transition-transform duration-240 rounded';
  const drawerVisible = 'opacity-100 md:translate-x-0 translate-y-0';
  const drawerHidden = 'opacity-0 md:translate-x-full translate-y-full pointer-events-none';

  return (
    <div className={`${overlayClass} md:items-start md:justify-end items-end justify-center`}>
      <button
        type="button"
        aria-label="議事録を閉じる"
        className="absolute inset-0"
        onClick={handleClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${taskId} の議事録`}
        className={`${drawerBase} z-10 ${isVisible ? drawerVisible : drawerHidden}`}
      >
        <button
          aria-label="議事録を閉じる"
          onClick={handleClose}
          className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-[var(--muted)] hover:bg-slate-100"
        >
          ✕
        </button>
        {/* drag handle for mobile bottom sheet */}
        <div className="md:hidden mb-3 flex items-center justify-center">
          <div className="w-12 h-1.5 bg-slate-300 rounded-full" />
        </div>
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">
              {taskName && taskName.length > 0 ? taskName : 'Minutes'}
            </h2>
            <div className="text-xs text-[var(--muted)]">
              タスク:{' '}
              <button
                onClick={handleCopyTaskId}
                title="タスク ID をコピー"
                className="inline-block text-[var(--muted)] hover:underline focus:outline-none"
              >
                {taskId}
              </button>
            </div>
          </div>
          <div>
            <button
              onClick={async () => {
                const newName = window.prompt('このタスクの新しい名前', taskName || '');
                if (!newName) return;
                try {
                  await renameBgTask(taskId, newName);
                  setTaskName(newName);
                  toast.addToast('名前を変更しました', { level: 'success' });
                } catch (e: unknown) {
                  toast.addToast(errorMessage(e, '名前の変更に失敗しました'), { level: 'error' });
                }
              }}
              className="rounded bg-slate-100 px-2 py-1 text-sm"
            >
              名前を変更
            </button>
          </div>
        </div>
        {/* Screen-reader live region for action feedback (polite) */}
        <div aria-live="polite" role="status" aria-atomic="true" className="sr-only">
          {liveMessage}
        </div>
        {/* Visual toast for live messages (also accessible) */}
        <Toast message={liveMessage} onClose={() => setLiveMessage(null)} />
        <div>
          {loading && <div className="p-4">議事録を読み込み中…</div>}
          {error && <div className="p-4 text-sm text-red-600">{error}</div>}
          {text && (
            <div>
              {!transcriptOnly && (
                <>
                  <div className="mb-3 text-sm text-[var(--muted)]">要約</div>
                  <MarkdownBody
                    className="mb-4 rounded bg-slate-50 p-3 text-sm"
                    text={summary && summary.length > 0 ? summary : text.slice(0, 1000)}
                  />
                </>
              )}
              <SpeakerEditor
                taskId={taskId}
                segments={segments}
                onSaved={(_transcript, nextSegments) => {
                  setSegments(nextSegments);
                  toast.addToast('話者名を保存しました', { level: 'success' });
                }}
                onError={(message) => toast.addToast(message, { level: 'error' })}
              />
              <div className="mb-3 text-sm text-[var(--muted)]">全文</div>
              <MarkdownBody className="mb-4 rounded bg-slate-50 p-3 text-sm" text={text} />
              <div className="mt-4">
                <div
                  className="drawer-footer flex flex-wrap gap-2 justify-center border-t pt-3 mt-4 md:mt-6 md:border-t-0 md:pt-0"
                  style={{ paddingBottom: 'calc(12px + env(safe-area-inset-bottom))' }}
                >
                  {!transcriptOnly && (
                    <button
                      onClick={() =>
                        startDownload(
                          () => fetchMinutesDocx(taskId),
                          `${taskId}_minutes.docx`,
                          toast.addToast
                        )
                      }
                      className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm"
                    >
                      Word 議事録
                    </button>
                  )}

                  <button
                    onClick={() =>
                      startDownload(
                        () => fetchTranscriptDownload(taskId, 'txt'),
                        `${taskId}_transcript.txt`,
                        toast.addToast
                      )
                    }
                    className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded bg-[var(--accent)] px-3 py-2 text-sm text-white"
                  >
                    文字起こしをダウンロード
                  </button>

                  {!transcriptOnly && (
                    <button
                      onClick={() =>
                        startDownload(
                          () => fetchSummaryDownload(taskId, 'txt'),
                          `${taskId}_summary.txt`,
                          toast.addToast
                        )
                      }
                      className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm"
                    >
                      要約をダウンロード
                    </button>
                  )}

                  {!transcriptOnly && (
                    <button
                      onClick={() =>
                        startDownload(
                          () => fetchActionItemsDownload(taskId, 'json'),
                          `${taskId}_action_items.json`,
                          toast.addToast
                        )
                      }
                      className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm"
                    >
                      アクションアイテムをダウンロード
                    </button>
                  )}

                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(text);
                        toast.addToast(
                          transcriptOnly
                            ? '文字起こしをコピーしました'
                            : '議事録をクリップボードにコピーしました',
                          {
                            level: 'success',
                          }
                        );
                      } catch {
                        // clipboard permission can be denied
                        toast.addToast('コピーに失敗しました', { level: 'error' });
                      }
                    }}
                    className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm"
                  >
                    コピー
                  </button>

                  <button
                    onClick={handleCopyLink}
                    className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm"
                  >
                    リンクをコピー
                  </button>
                  {isAdmin && (
                    <button
                      onClick={handleDelete}
                      className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                    >
                      削除
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {isAdmin && !text && (
          <div className="mt-4 flex justify-center">
            <button
              onClick={handleDelete}
              className="rounded border px-3 py-2 text-sm text-red-600 hover:bg-red-50"
            >
              削除
            </button>
          </div>
        )}
      </aside>
      <ConfirmDialog
        open={confirmOpen}
        title={error === STILL_PROCESSING ? '議事録を強制削除' : '議事録を削除'}
        message={
          error === STILL_PROCESSING
            ? '議事録はまだ処理中です。強制削除すると成果物と記録が消え、元に戻せません。'
            : 'この議事録を削除しますか？元に戻せます。'
        }
        onConfirm={() => {
          setConfirmOpen(false);
          handleDeleteConfirmed();
        }}
        onCancel={() => setConfirmOpen(false)}
        confirmLabel={error === STILL_PROCESSING ? '強制削除' : '削除'}
        cancelLabel="キャンセル"
      />
    </div>
  );
}

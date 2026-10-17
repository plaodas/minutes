import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';

import { getBgTasks } from '../api/client';
import { useTasks } from '../hooks/useTasks';
import { getTasksPageLimit } from '../lib/apiConfig';
import { minutesHash, minutesTaskIdFromHash } from '../lib/minutesLink';
import { toHistoryItem } from '../lib/taskState';
import type { HistoryItem, TaskHistoryPreview } from '../lib/taskState';

import HistoryEventsModal from './HistoryEventsModal';
import HistoryList from './HistoryList';
import { MinutesDrawer } from './MinutesDrawer';

export function HistoryView({ onCreate }: { onCreate: () => void }) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalTask, setModalTask] = useState<string | null>(null);
  const linkedTaskId = minutesTaskIdFromHash(window.location.hash);
  const [minutesTask, setMinutesTask] = useState<string | null>(linkedTaskId);
  const [isMinutesVisible, setIsMinutesVisible] = useState(linkedTaskId !== null);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const prevFocusRef = useRef<HTMLElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const { tasks, loading: tasksLoading, error: tasksError, reload } = useTasks();

  useEffect(() => {
    setLoading(tasksLoading);
  }, [tasksLoading]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearchQuery(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (searchQuery.length >= 2) return;
    if (tasks && Array.isArray(tasks)) {
      const arr = tasks.map(toHistoryItem);
      setItems(arr);
      setHasMore(arr.length >= getTasksPageLimit());
    }
  }, [tasks, searchQuery]);

  useEffect(() => {
    if (searchQuery.length < 2) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const limit = getTasksPageLimit();
        const nextTasks = await getBgTasks({ q: searchQuery, limit, offset: 0 });
        if (cancelled) return;
        setItems(nextTasks.map(toHistoryItem));
        setHasMore(nextTasks.length >= limit);
      } catch {
        if (!cancelled) setHasMore(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [searchQuery]);

  useEffect(() => {
    if (modalTask) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [modalTask]);

  useEffect(() => {
    const openLinkedMinutes = () => {
      const taskId = minutesTaskIdFromHash(window.location.hash);
      if (!taskId) return;
      setMinutesTask(taskId);
      setIsMinutesVisible(true);
    };
    window.addEventListener('hashchange', openLinkedMinutes);
    return () => window.removeEventListener('hashchange', openLinkedMinutes);
  }, []);

  const openMinutes = (taskId: string) => {
    setMinutesTask(taskId);
    setIsMinutesVisible(true);
    const nextHash = minutesHash(taskId);
    if (window.location.hash !== nextHash) window.location.hash = nextHash;
  };

  const closeMinutes = () => {
    const taskId = minutesTask;
    setIsMinutesVisible(false);
    setMinutesTask(null);
    if (taskId && minutesTaskIdFromHash(window.location.hash) === taskId) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    }
  };

  const handleEventsLoaded = useCallback((taskId: string, events: TaskHistoryPreview[]) => {
    setItems((prev) =>
      prev.map((item) => (item.id === taskId ? { ...item, histories: events } : item))
    );
  }, []);

  const handleRenamed = useCallback((taskId: string, name: string) => {
    setItems((prev) => prev.map((item) => (item.id === taskId ? { ...item, name } : item)));
  }, []);

  const openModal = (id: string) => {
    prevFocusRef.current = document.activeElement as HTMLElement | null;
    setModalTask(id);
  };

  const closeModal = () => {
    setModalTask(null);
    try {
      prevFocusRef.current?.focus();
    } catch {
      // previously focused node may no longer be in the document
    }
  };

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting || loadingMore || !hasMore) return;
          setLoadingMore(true);
          void (async () => {
            try {
              const limit = getTasksPageLimit();
              const offset = items.length;
              if (offset === 0) return;
              const nextTasks = await getBgTasks({
                limit,
                offset,
                q: searchQuery.length >= 2 ? searchQuery : undefined,
              });
              const arr = nextTasks.map(toHistoryItem);
              setItems((prev) => [...prev, ...arr]);
              setHasMore(arr.length >= limit);
            } catch {
              // load-more errors can be retried via the history reload button
            } finally {
              setLoadingMore(false);
            }
          })();
        }
      },
      { root: null, rootMargin: '200px' }
    );
    obs.observe(sentinel);
    return () => obs.disconnect();
  }, [hasMore, items, loadingMore, searchQuery]);

  return (
    <>
      <section>
        <div className="mb-7 flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-[var(--accent)]">アーカイブ</p>
            <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">最近の議事録</h1>
          </div>
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white shadow-sm hover:brightness-95"
          >
            <Plus size={17} /> 新規アップロード
          </button>
        </div>
        <label className="mb-4 block">
          <span className="sr-only">議事録を検索</span>
          <input
            aria-label="議事録を検索"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="名前、要約、本文で検索"
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
        </label>

        {tasksError && (
          <div
            className={`mb-4 rounded-md p-3 border ${items.length > 0 ? 'bg-yellow-50 border-yellow-200' : 'bg-rose-50 border-rose-200'}`}
          >
            <div className="flex items-center justify-between gap-4">
              <div className="text-sm">
                {items.length > 0 ? (
                  <span>最新の履歴を取得できませんでした。以前のデータを表示しています。</span>
                ) : (
                  <span>履歴の読み込みに失敗しました。ネットワーク接続を確認してください。</span>
                )}
              </div>
              <div className="shrink-0">
                <button
                  onClick={() => reload()}
                  className={`rounded px-3 py-1 text-sm font-medium text-white ${items.length > 0 ? 'bg-yellow-600 hover:brightness-90' : 'bg-rose-600 hover:brightness-90'}`}
                >
                  再試行
                </button>
              </div>
            </div>
          </div>
        )}

        <HistoryList
          items={items}
          sentinelRef={sentinelRef}
          onOpenMinutes={openMinutes}
          onOpenEvents={openModal}
        />

        <p className="mt-3 text-xs text-[var(--muted)]">
          {loading ? '履歴を読み込み中…' : '履歴はサーバーから読み込んでいます。'}
        </p>
      </section>

      {modalTask && (
        <HistoryEventsModal
          taskId={modalTask}
          item={items.find((item) => item.id === modalTask)}
          onClose={closeModal}
          onEventsLoaded={handleEventsLoaded}
          onRenamed={handleRenamed}
        />
      )}
      {minutesTask && isMinutesVisible && (
        <MinutesDrawer taskId={minutesTask} onClose={closeMinutes} />
      )}
    </>
  );
}

export default HistoryView;

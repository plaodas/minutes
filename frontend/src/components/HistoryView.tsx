import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';

import { getBgTasks } from '../api/client';
import { useTasks } from '../hooks/useTasks';
import { getTasksPageLimit } from '../lib/apiConfig';
import { toHistoryItem } from '../lib/taskState';
import type { HistoryItem, TaskHistoryPreview } from '../lib/taskState';

import HistoryEventsModal from './HistoryEventsModal';
import HistoryList from './HistoryList';
import { MinutesDrawer } from './MinutesDrawer';

export function HistoryView({ onCreate }: { onCreate: () => void }) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalTask, setModalTask] = useState<string | null>(null);
  const [minutesTask, setMinutesTask] = useState<string | null>(null);
  const [isMinutesVisible, setIsMinutesVisible] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const prevFocusRef = useRef<HTMLElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const { tasks, loading: tasksLoading, error: tasksError, reload } = useTasks();

  useEffect(() => {
    setLoading(tasksLoading);
  }, [tasksLoading]);

  useEffect(() => {
    if (tasks && Array.isArray(tasks)) {
      const arr = tasks.map(toHistoryItem);
      setItems(arr);
      setHasMore(arr.length >= getTasksPageLimit());
    }
  }, [tasks]);

  useEffect(() => {
    if (modalTask) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [modalTask]);

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
              const nextTasks = await getBgTasks({ limit, offset });
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
  }, [hasMore, items, loadingMore]);

  return (
    <>
      <section>
        <div className="mb-7 flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-[var(--accent)]">Workspace archive</p>
            <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Recent minutes</h1>
          </div>
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white shadow-sm hover:brightness-95"
          >
            <Plus size={17} /> New upload
          </button>
        </div>

        {tasksError && (
          <div
            className={`mb-4 rounded-md p-3 border ${items.length > 0 ? 'bg-yellow-50 border-yellow-200' : 'bg-rose-50 border-rose-200'}`}
          >
            <div className="flex items-center justify-between gap-4">
              <div className="text-sm">
                {items.length > 0 ? (
                  <span>Could not retrieve the latest history. Displaying older data.</span>
                ) : (
                  <span>Failed to load history. Please check your network connection.</span>
                )}
              </div>
              <div className="shrink-0">
                <button
                  onClick={() => reload()}
                  className={`rounded px-3 py-1 text-sm font-medium text-white ${items.length > 0 ? 'bg-yellow-600 hover:brightness-90' : 'bg-rose-600 hover:brightness-90'}`}
                >
                  Retry
                </button>
              </div>
            </div>
          </div>
        )}

        <HistoryList
          items={items}
          sentinelRef={sentinelRef}
          onOpenMinutes={(id) => {
            setMinutesTask(id);
            setIsMinutesVisible(true);
          }}
          onOpenEvents={openModal}
        />

        <p className="mt-3 text-xs text-[var(--muted)]">
          {loading ? 'Loading history...' : 'History is loaded from the backend.'}
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
        <MinutesDrawer
          taskId={minutesTask}
          onClose={() => {
            setIsMinutesVisible(false);
            setMinutesTask(null);
          }}
        />
      )}
    </>
  );
}

export default HistoryView;

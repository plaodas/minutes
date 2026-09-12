import React, { useEffect, useState } from 'react';

import { getBgTaskEvents, renameBgTask } from '../api/client';
import { API_BASE } from '../lib/apiConfig';
import type { HistoryItem, TaskHistoryPreview } from '../lib/taskState';

type Props = {
  taskId: string;
  item?: HistoryItem;
  onClose: () => void;
  onEventsLoaded: (taskId: string, events: TaskHistoryPreview[]) => void;
  onRenamed: (taskId: string, name: string) => void;
};

export default function HistoryEventsModal({
  taskId,
  item,
  onClose,
  onEventsLoaded,
  onRenamed,
}: Props) {
  const [visible, setVisible] = useState(false);
  const events = item?.histories || [];

  useEffect(() => {
    const show = window.setTimeout(() => setVisible(true), 10);
    return () => window.clearTimeout(show);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getBgTaskEvents(taskId);
        if (!cancelled) onEventsLoaded(taskId, loaded);
      } catch {
        // keep preview events if the full history request fails
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onEventsLoaded, taskId]);

  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;

  const close = React.useCallback(() => {
    setVisible(false);
    window.setTimeout(() => onCloseRef.current(), 220);
  }, []);

  useEffect(() => {
    const root = document.querySelector('[role="dialog"]') as HTMLElement | null;
    const getFocusable = () => {
      if (!root) return [] as HTMLElement[];
      const selector =
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';
      return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
        (el) => !el.hasAttribute('disabled')
      );
    };
    const focusTimer = window.setTimeout(() => {
      const closeBtn = document.querySelector(
        '[role="dialog"] button[aria-label="Close"]'
      ) as HTMLElement | null;
      if (closeBtn) {
        closeBtn.focus();
        return;
      }
      getFocusable()[0]?.focus();
    }, 50);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== 'Tab') return;
      const list = getFocusable();
      if (list.length === 0) {
        e.preventDefault();
        return;
      }
      const idx = list.indexOf(document.activeElement as HTMLElement);
      if (e.shiftKey) {
        if (idx <= 0) {
          e.preventDefault();
          list[list.length - 1].focus();
        }
      } else if (idx === list.length - 1) {
        e.preventDefault();
        list[0].focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('keydown', onKey);
    };
  }, [close, taskId]);

  return (
    <div
      className={`fixed inset-0 z-50 flex items-start justify-center p-6 transition-opacity duration-200 ${visible ? 'bg-black/40 opacity-100' : 'bg-black/0 opacity-0'}`}
    >
      <button
        type="button"
        aria-label="Close full history"
        className="absolute inset-0"
        onClick={close}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Full history for ${taskId}`}
        className={`relative z-10 max-h-[80vh] w-full max-w-2xl overflow-auto rounded bg-white p-6 transform transition-all duration-200 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'}`}
      >
        <button
          aria-label="Close"
          onClick={close}
          className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-[var(--muted)] hover:bg-slate-100"
        >
          ✕
        </button>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Full history for {item?.name || taskId}</h2>
          <div>
            <button
              data-testid={`rename-${taskId}`}
              onClick={async () => {
                const newName = window.prompt('Enter new name for this task', item?.name || '');
                if (!newName) return;
                try {
                  await renameBgTask(taskId, newName);
                  onRenamed(taskId, newName);
                } catch {
                  // rename errors are shown by the API client throw path
                }
              }}
              className="mr-3 rounded bg-slate-100 px-2 py-1 text-sm"
            >
              Rename
            </button>
          </div>
        </div>
        <div>
          {events.map((h, idx) => (
            <div key={idx} className="mb-4 border-b pb-3">
              <div className="flex items-center justify-between">
                <div className="text-sm text-[var(--muted)]">
                  {h.event_ts ? new Date(h.event_ts).toLocaleString() : ''}
                </div>
                <div className="text-sm font-medium">{h.event_type}</div>
              </div>
              <div className="mt-2 text-xs">
                <pre className="rounded bg-slate-50 p-2 text-xs">
                  {JSON.stringify(h.payload, null, 2)}
                </pre>
                {h.payload?.result?.output_file && (
                  <div className="mt-2 text-sm">
                    <a
                      target="_blank"
                      rel="noreferrer"
                      href={`${API_BASE}/${h.payload.result.output_file}`}
                    >
                      Open output file
                    </a>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div className="mt-4">
            <div className="text-sm text-[var(--muted)]">All events loaded</div>
          </div>
        </div>
      </div>
    </div>
  );
}

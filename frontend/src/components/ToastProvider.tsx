import React, { createContext, useContext, useMemo, useState, useEffect } from 'react';

import { deleteTask, undeleteTask } from '../api/client';
import type { ConfirmDeleteDetail } from '../lib/appEvents';
import { dispatchTaskChanged } from '../lib/appEvents';

import Toast from './Toast';
import ConfirmDialog from './ConfirmDialog';

type ToastItem = {
  id: string;
  message: string;
  duration?: number;
  level?: 'info' | 'success' | 'error';
  actionLabel?: string;
  action?: () => void;
};

type ToastContext = {
  addToast: (
    message: string,
    opts?:
      | number
      | {
          duration?: number;
          level?: 'info' | 'success' | 'error';
          actionLabel?: string;
          action?: () => void;
        }
  ) => string;
  removeToast: (id: string) => void;
};

const ctx = createContext<ToastContext | null>(null);

export function useToast() {
  const c = useContext(ctx);
  if (!c) throw new Error('useToast must be used within ToastProvider');
  return c;
}

export function ToastProvider({
  children,
  maxVisible = 3,
}: {
  children: React.ReactNode;
  maxVisible?: number;
}) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [queue, setQueue] = useState<ToastItem[]>([]);

  const addToast = (
    message: string,
    opts?:
      | number
      | {
          duration?: number;
          level?: 'info' | 'success' | 'error';
          actionLabel?: string;
          action?: () => void;
        }
  ) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    let duration = 3500;
    let level: 'info' | 'success' | 'error' = 'info';
    let actionLabel: string | undefined;
    let action: (() => void) | undefined;
    if (typeof opts === 'number') duration = opts;
    else if (opts) {
      duration = opts.duration ?? duration;
      level = opts.level ?? level;
      actionLabel = opts.actionLabel;
      action = opts.action;
    }
    const item: ToastItem = { id, message, duration, level, actionLabel, action };
    setToasts((cur) => {
      if (cur.length < maxVisible) return [...cur, item];
      // enqueue
      setQueue((q) => [...q, item]);
      return cur;
    });
    return id;
  };

  const removeToast = (id: string) => {
    setToasts((cur) => cur.filter((t) => t.id !== id));
    setQueue((q) => {
      if (q.length === 0) return q;
      const [next, ...rest] = q;
      setToasts((cur) => [...cur, next]);
      return rest;
    });
  };

  const value = useMemo(() => ({ addToast, removeToast }), []);
  // Global confirm dialog bridge: listen for 'app:confirm-delete' events
  const ConfirmBridge = () => {
    const { addToast } = useToast();
    const [open, setOpen] = useState(false);
    const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);

    useEffect(() => {
      const handler = (e: Event) => {
        const detail = (e as CustomEvent<ConfirmDeleteDetail>).detail;
        setPendingTaskId(detail?.taskId || null);
        setOpen(true);
      };
      window.addEventListener('app:confirm-delete', handler);
      return () => window.removeEventListener('app:confirm-delete', handler);
    }, []);

    const doConfirm = async () => {
      if (!pendingTaskId) return;
      try {
        await deleteTask(pendingTaskId);
        addToast('削除しました', {
          level: 'success',
          actionLabel: '元に戻す',
          action: async () => {
            try {
              await undeleteTask(pendingTaskId);
              addToast('復元しました', { level: 'success' });
            } catch {
              // restore is best-effort from the undo toast
              addToast('復元に失敗しました', { level: 'error' });
            }
          },
        });
        dispatchTaskChanged(pendingTaskId, 'deleted');
      } catch {
        addToast('削除に失敗しました', { level: 'error' });
      } finally {
        setOpen(false);
        setPendingTaskId(null);
      }
    };

    return (
      <ConfirmDialog
        open={open}
        title="議事録を削除"
        message="この議事録を削除しますか？元に戻せます。"
        onConfirm={doConfirm}
        onCancel={() => setOpen(false)}
        confirmLabel="削除"
        cancelLabel="キャンセル"
      />
    );
  };

  return (
    <ctx.Provider value={value}>
      {children}
      {/* Toast stack container */}
      <div className="fixed right-4 top-12 z-50 flex flex-col gap-3 pointer-events-none">
        {toasts.map((t) => (
          <Toast
            key={t.id}
            message={t.message}
            duration={t.duration}
            onClose={() => removeToast(t.id)}
            placementClassName=""
            level={t.level}
            actionLabel={t.actionLabel}
            action={t.action}
          />
        ))}
      </div>
      <ConfirmBridge />
    </ctx.Provider>
  );
}

export default ToastProvider;

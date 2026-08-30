import React, { createContext, useContext, useMemo, useState } from 'react'
import Toast from './Toast'

type ToastItem = { id: string; message: string; duration?: number; level?: 'info' | 'success' | 'error'; actionLabel?: string; action?: (() => void) }

type ToastContext = {
  addToast: (message: string, opts?: number | { duration?: number; level?: 'info' | 'success' | 'error'; actionLabel?: string; action?: (() => void) }) => string
  removeToast: (id: string) => void
}

const ctx = createContext<ToastContext | null>(null)

export function useToast() {
  const c = useContext(ctx)
  if (!c) throw new Error('useToast must be used within ToastProvider')
  return c
}

export function ToastProvider({ children, maxVisible = 3 }: { children: React.ReactNode; maxVisible?: number }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [queue, setQueue] = useState<ToastItem[]>([])

  const addToast = (message: string, opts?: number | { duration?: number; level?: 'info' | 'success' | 'error'; actionLabel?: string; action?: (() => void) }) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    let duration = 3500
    let level: 'info' | 'success' | 'error' = 'info'
    let actionLabel: string | undefined
    let action: (() => void) | undefined
    if (typeof opts === 'number') duration = opts
    else if (opts) {
      duration = opts.duration ?? duration
      level = opts.level ?? level
      actionLabel = opts.actionLabel
      action = opts.action
    }
    const item: ToastItem = { id, message, duration, level, actionLabel, action }
    setToasts((cur) => {
      if (cur.length < maxVisible) return [...cur, item]
      // enqueue
      setQueue((q) => [...q, item])
      return cur
    })
    return id
  }

  const removeToast = (id: string) => {
    setToasts((cur) => cur.filter((t) => t.id !== id))
    setQueue((q) => {
      if (q.length === 0) return q
      const [next, ...rest] = q
      setToasts((cur) => [...cur, next])
      return rest
    })
  }

  const value = useMemo(() => ({ addToast, removeToast }), [])

  return (
    <ctx.Provider value={value}>
      {children}
      {/* Toast stack container */}
      <div className="fixed right-4 top-12 z-50 flex flex-col gap-3 pointer-events-none">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} duration={t.duration} onClose={() => removeToast(t.id)} placementClassName="" />
        ))}
      </div>
    </ctx.Provider>
  )
}

export default ToastProvider

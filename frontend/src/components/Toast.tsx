import React, { useEffect, useState } from 'react'

type ToastProps = {
  message: string | null
  duration?: number
  onClose?: () => void
  // optional placement classes, e.g. "right-4 top-12"
  placementClassName?: string
  level?: 'info' | 'success' | 'error'
  actionLabel?: string
  action?: (() => void)
}

export default function Toast({ message, duration = 3500, onClose, placementClassName = 'right-4 top-12', level = 'info', actionLabel, action }: ToastProps) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!message) {
      setVisible(false)
      return
    }
    // show
    // small delay so CSS transition runs
    const t = setTimeout(() => setVisible(true), 20)

    // auto-hide
    const hide = setTimeout(() => {
      setVisible(false)
      // call onClose after animation
      setTimeout(() => { if (onClose) onClose() }, 220)
    }, duration)

    return () => { clearTimeout(t); clearTimeout(hide) }
  }, [message, duration, onClose])

  if (!message) return null

  const wrapperClass = placementClassName ? `absolute ${placementClassName} z-50 pointer-events-none` : 'pointer-events-none'
  const bgClass = level === 'success' ? 'bg-emerald-600' : level === 'error' ? 'bg-rose-600' : 'bg-black/85'

  return (
    <div className={wrapperClass}>
      <div role="status" aria-live="polite" aria-atomic="true" className={`pointer-events-auto rounded ${bgClass} text-white px-3 py-2 text-sm shadow-lg flex items-center gap-3 transform transition-all duration-200 ease-out ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}`}>
        <div className="flex-1">{message}</div>
        {actionLabel && action && (
          <button aria-label={actionLabel} onClick={() => { try { action() } finally { setVisible(false); setTimeout(() => { if (onClose) onClose() }, 220) } }} className="ml-2 rounded bg-white/10 px-2 py-1 text-xs font-medium hover:bg-white/20">{actionLabel}</button>
        )}
        <button aria-label="Close notification" onClick={() => { setVisible(false); setTimeout(() => { if (onClose) onClose() }, 220) }} className="ml-2 rounded px-2 py-1 text-xs font-medium hover:bg-white/10">✕</button>
      </div>
    </div>
  )
}

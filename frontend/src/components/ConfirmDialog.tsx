import React, { useEffect, useRef } from 'react'

export default function ConfirmDialog({ open, title, message, onConfirm, onCancel, confirmLabel = 'Confirm', cancelLabel = 'Cancel' } : {
  open: boolean,
  title?: string,
  message?: string,
  onConfirm: () => void,
  onCancel: () => void,
  confirmLabel?: string,
  cancelLabel?: string,
}){
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const confirmRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    // focus the cancel button by default
    const toFocus = cancelRef.current || confirmRef.current || dialogRef.current
    ;(toFocus as HTMLElement | null)?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
        return
      }
      if (e.key === 'Tab') {
        // simple focus trap
        const nodes = dialogRef.current?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") || []
        if (nodes.length === 0) return
        const first = nodes[0]
        const last = nodes[nodes.length - 1]
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault()
            last.focus()
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault()
            first.focus()
          }
        }
      }
    }

    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-70 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
      <div ref={dialogRef} tabIndex={-1} className="w-full max-w-lg bg-white rounded p-4 shadow-lg">
        {title && <h3 className="text-lg font-semibold mb-2">{title}</h3>}
        {message && <div className="text-sm text-[var(--muted)] mb-4">{message}</div>}
        <div className="flex justify-end gap-2">
          <button ref={cancelRef} onClick={onCancel} className="rounded border px-3 py-2 text-sm">{cancelLabel}</button>
          <button ref={confirmRef} onClick={onConfirm} className="rounded bg-red-600 px-3 py-2 text-sm text-white">{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

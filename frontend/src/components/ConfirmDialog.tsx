import React from 'react'

export default function ConfirmDialog({ open, title, message, onConfirm, onCancel, confirmLabel = 'Confirm', cancelLabel = 'Cancel' } : {
  open: boolean,
  title?: string,
  message?: string,
  onConfirm: () => void,
  onCancel: () => void,
  confirmLabel?: string,
  cancelLabel?: string,
}){
  if (!open) return null
  return (
    <div className="fixed inset-0 z-70 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg bg-white rounded p-4 shadow-lg">
        {title && <h3 className="text-lg font-semibold mb-2">{title}</h3>}
        {message && <div className="text-sm text-[var(--muted)] mb-4">{message}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="rounded border px-3 py-2 text-sm">{cancelLabel}</button>
          <button onClick={onConfirm} className="rounded bg-red-600 px-3 py-2 text-sm text-white">{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

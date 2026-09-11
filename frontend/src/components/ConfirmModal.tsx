import React from 'react'

interface ConfirmModalProps {
  open: boolean
  title?: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = 'OK',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded bg-white p-4 shadow">
        {title && <div className="text-lg font-semibold">{title}</div>}
        <div className="mt-2 text-sm text-[var(--muted)]">{message}</div>
        <div className="mt-4 flex justify-end gap-2">
          <button className="rounded border px-3 py-1" onClick={onCancel}>{cancelLabel}</button>
          <button className="rounded bg-red-600 px-3 py-1 text-white" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

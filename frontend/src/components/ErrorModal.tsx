import React from 'react'

export default function ErrorModal({ open, onClose, title, content }: { open: boolean; onClose: () => void; title?: string; content?: string | null }) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 w-[min(92%,720px)] rounded-md bg-white p-4 shadow-lg">
        <div className="flex items-start justify-between">
          <h3 className="text-lg font-semibold">{title || 'Details'}</h3>
          <button aria-label="close" onClick={onClose} className="rounded p-1 text-sm text-[var(--muted)] hover:bg-[var(--bg-default)]">✕</button>
        </div>
        <div className="mt-3 max-h-[60vh] overflow-auto rounded-sm border border-slate-100 bg-slate-50 p-3 font-mono text-xs whitespace-pre-wrap">
          {content ?? 'No details available.'}
        </div>
        <div className="mt-3 flex justify-end">
          <button onClick={onClose} className="rounded bg-[var(--accent)] px-3 py-1 text-sm font-medium text-white">Close</button>
        </div>
      </div>
    </div>
  )
}

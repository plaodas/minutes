import React, { useEffect, useState } from 'react'

export function MinutesDrawer({ taskId, onClose }: { taskId: string | null, onClose: () => void }) {
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!taskId) return
    const fetchMinutes = async () => {
      setLoading(true)
      setError(null)
      setText(null)
      try {
        const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
        const res = await fetch(`${BASE}/bg/minutes/${taskId}`)
        if (res.status === 202) {
          setError('Minutes are still processing')
          return
        }
        if (!res.ok) {
          const j = await res.json().catch(() => ({}))
          setError(j?.error || `failed to load minutes (${res.status})`)
          return
        }
        const txt = await res.text()
        setText(txt)
      } catch (e: any) {
        setError(e.message || 'fetch error')
      } finally {
        setLoading(false)
      }
    }
    fetchMinutes()
  }, [taskId])

  if (!taskId) return null
  return (
    <div onClick={(e) => { if (e.target === e.currentTarget) onClose() }} className="fixed inset-0 z-60 flex items-start justify-end p-6 transition-opacity duration-200 bg-black/40">
      <aside role="dialog" aria-modal="true" aria-label={`Minutes for ${taskId}`} className="relative max-h-[90vh] w-full max-w-2xl overflow-auto rounded bg-white p-6 transform transition-all duration-200">
        <button aria-label="Close minutes" onClick={onClose} className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-[var(--muted)] hover:bg-slate-100">✕</button>
        <div className="mb-3">
          <h2 className="text-lg font-semibold">Minutes</h2>
          <div className="text-xs text-[var(--muted)]">Task: {taskId}</div>
        </div>
        <div>
          {loading && <div className="p-4">Loading minutes…</div>}
          {error && <div className="p-4 text-sm text-red-600">{error}</div>}
          {text && (
            <div>
              <div className="mb-3 text-sm text-[var(--muted)]">Summary</div>
              <div className="mb-4 rounded bg-slate-50 p-3 text-sm whitespace-pre-wrap">{text.slice(0, 1000)}</div>
              <div className="mb-3 text-sm text-[var(--muted)]">Full text</div>
              <div className="mb-4 rounded bg-slate-50 p-3 text-sm whitespace-pre-wrap">{text}</div>
              <div className="flex gap-2">
                <button onClick={() => {
                  const blob = new Blob([text], { type: 'text/plain' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `${taskId}.txt`
                  document.body.appendChild(a)
                  a.click()
                  a.remove()
                  URL.revokeObjectURL(url)
                }} className="rounded bg-[var(--accent)] px-3 py-2 text-sm text-white">Download</button>

                <button onClick={async () => {
                  try { await navigator.clipboard.writeText(text); alert('Copied to clipboard') } catch { alert('Copy failed') }
                }} className="rounded border px-3 py-2 text-sm">Copy</button>

                <button onClick={() => { location.hash = `#minutes=${taskId}` }} className="rounded border px-3 py-2 text-sm">Copy link</button>
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

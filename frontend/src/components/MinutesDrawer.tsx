import React, { useEffect, useState } from 'react'
import { fetchTranscriptDownload, fetchSummaryDownload, fetchActionItemsDownload } from '../api/client'

export function MinutesDrawer({ taskId, onClose }: { taskId: string | null, onClose: () => void }) {
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [liveMessage, setLiveMessage] = useState<string | null>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (!taskId) return
    // show with animation on mount
    const t = setTimeout(() => setIsVisible(true), 20)
    return () => clearTimeout(t)
  }, [taskId])

  // focus management: move focus to close button when visible
  useEffect(() => {
    if (!isVisible) return
    const timeout = setTimeout(() => {
      const btn = document.querySelector('[aria-label="Close minutes"]') as HTMLElement | null
      if (btn) try { btn.focus() } catch {}
    }, 50)
    return () => clearTimeout(timeout)
  }, [isVisible])

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

  const handleClose = () => {
    setIsVisible(false)
    // wait for animation to finish then call onClose
    setTimeout(() => onClose(), 260)
  }

  if (!taskId) return null
  return (
    <div onClick={(e) => { if (e.target === e.currentTarget) handleClose() }} className={`fixed inset-0 z-60 flex items-start justify-end p-6 transition-colors duration-200 ${isVisible ? 'bg-black/40' : 'bg-black/0 pointer-events-auto'}`}>
      <aside role="dialog" aria-modal="true" aria-label={`Minutes for ${taskId}`} className={`relative max-h-[90vh] w-full max-w-2xl overflow-auto rounded bg-white p-6 transform transition-transform duration-240 ${isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}`}>
        <button aria-label="Close minutes" onClick={handleClose} className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-[var(--muted)] hover:bg-slate-100">✕</button>
        <div className="mb-3">
          <h2 className="text-lg font-semibold">Minutes</h2>
          <div className="text-xs text-[var(--muted)]">Task: {taskId}</div>
        </div>
        {/* Screen-reader live region for action feedback (polite) */}
        <div aria-live="polite" role="status" aria-atomic="true" className="sr-only">{liveMessage}</div>
        {/* Visual toast for live messages (also accessible) */}
        {liveMessage && (
          <div className="absolute right-4 top-12 z-50 pointer-events-auto">
            <div role="status" aria-live="polite" aria-atomic="true" className="rounded bg-black/85 text-white px-3 py-2 text-sm shadow-lg transition-opacity duration-200">
              {liveMessage}
            </div>
          </div>
        )}
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
                <button onClick={async () => {
                  try {
                    const { blob } = await fetchTranscriptDownload(taskId, 'txt')
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${taskId}_transcript.txt`
                    document.body.appendChild(a)
                    a.click()
                    a.remove()
                    URL.revokeObjectURL(url)
                    setLiveMessage('Transcript download started')
                    setTimeout(() => setLiveMessage(null), 3500)
                  } catch (e: any) { alert('Download failed: ' + (e?.message || e)) }
                }} className="rounded bg-[var(--accent)] px-3 py-2 text-sm text-white">Download transcript</button>

                <button onClick={async () => {
                  try {
                    const { blob } = await fetchSummaryDownload(taskId, 'txt')
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${taskId}_summary.txt`
                    document.body.appendChild(a)
                    a.click()
                    a.remove()
                    URL.revokeObjectURL(url)
                    setLiveMessage('Summary download started')
                    setTimeout(() => setLiveMessage(null), 3500)
                  } catch (e: any) { alert('Download failed: ' + (e?.message || e)) }
                }} className="rounded border px-3 py-2 text-sm">Download summary</button>

                <button onClick={async () => {
                  try {
                    const { blob } = await fetchActionItemsDownload(taskId, 'json')
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${taskId}_action_items.json`
                    document.body.appendChild(a)
                    a.click()
                    a.remove()
                    URL.revokeObjectURL(url)
                    setLiveMessage('Action items download started')
                    setTimeout(() => setLiveMessage(null), 3500)
                  } catch (e: any) { alert('Download failed: ' + (e?.message || e)) }
                }} className="rounded border px-3 py-2 text-sm">Download action items</button>

                <button onClick={async () => {
                  try { await navigator.clipboard.writeText(text); setLiveMessage('Copied minutes to clipboard'); setTimeout(() => setLiveMessage(null), 3000) } catch { setLiveMessage('Copy failed'); setTimeout(() => setLiveMessage(null), 3000) }
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

import React, { useEffect, useState } from 'react'
import Toast from './Toast'
import ConfirmDialog from './ConfirmDialog'
import { fetchTranscriptDownload, fetchSummaryDownload, fetchActionItemsDownload, deleteTask, undeleteTask } from '../api/client'
import { useToast } from './ToastProvider'
import startDownload from '../lib/download'

export function MinutesDrawer({ taskId, onClose }: { taskId: string | null, onClose: () => void }) {
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [liveMessage, setLiveMessage] = useState<string | null>(null)
  const [isVisible, setIsVisible] = useState(false)
  const toast = useToast()
  useEffect(() => {
    if (!taskId) return
    // allow mount to complete before showing for CSS transition
    const id = setTimeout(() => setIsVisible(true), 10)
    return () => clearTimeout(id)
  }, [taskId])
  useEffect(() => {
    if (!taskId) return
    const fetchMinutes = async () => {
      setLoading(true)
      setError(null)
      setText(null)
      const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
      try {
        const fetchWithRetry = (await import('../lib/fetchWithRetry')).default
        const res = await fetchWithRetry(`${BASE}/bg/minutes/${taskId}`, { credentials: 'same-origin' }, { retries: 2, timeoutMs: 10000 })
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

  const handleCopyLink = async () => {
    if (!taskId) {
      toast.addToast('Task id unavailable', { level: 'error' })
      return
    }
    const url = `${location.origin}${location.pathname}#minutes=${taskId}`
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url)
      } else {
        const ta = document.createElement('textarea')
        ta.value = url
        ta.setAttribute('readonly', '')
        ta.style.position = 'absolute'
        ta.style.left = '-9999px'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      toast.addToast('Copied link to clipboard', { level: 'success' })
      setLiveMessage('Link copied')
      setTimeout(() => setLiveMessage(null), 2000)
    } catch (e) {
      toast.addToast('Copy failed', { level: 'error' })
    }
  }

  const [confirmOpen, setConfirmOpen] = useState(false)
  const handleDeleteConfirmed = async () => {
    if (!taskId) return
    try {
      await deleteTask(taskId)
      toast.addToast('Deleted', { level: 'success', actionLabel: 'Undo', action: async () => { try { await undeleteTask(taskId); toast.addToast('Restored', { level: 'success' }) } catch { toast.addToast('Restore failed', { level: 'error' }) } } })
      // optionally close drawer
      setIsVisible(false)
      setTimeout(() => onClose(), 260)
        try {
          // notify app that task changed so history can refresh
          window.dispatchEvent(new CustomEvent('app:task-changed', { detail: { taskId, action: 'deleted' } }))
        } catch (e) {}
    } catch (e) {
      toast.addToast('Delete failed', { level: 'error' })
    }
  }

  const handleDelete = () => {
    setConfirmOpen(true)
  }

  if (!taskId) return null
  const overlayClass = `fixed inset-0 z-60 flex p-6 transition-colors duration-200 ${isVisible ? 'bg-black/40 pointer-events-auto' : 'bg-black/0 pointer-events-none'}`

  // The drawer behaves as a right-side panel on md+ and a bottom sheet on small screens.
  const drawerBase = 'relative max-h-[90vh] w-full max-w-2xl overflow-auto bg-white p-6 transform transition-transform duration-240 rounded'
  const drawerVisible = 'opacity-100 md:translate-x-0 translate-y-0'
  const drawerHidden = 'opacity-0 md:translate-x-full translate-y-full pointer-events-none'

  return (
    <div onClick={(e) => { if (e.target === e.currentTarget) handleClose() }} className={`${overlayClass} md:items-start md:justify-end items-end justify-center`}>
      <aside role="dialog" aria-modal="true" aria-label={`Minutes for ${taskId}`} className={`${drawerBase} ${isVisible ? drawerVisible : drawerHidden}`}>
        <button aria-label="Close minutes" onClick={handleClose} className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-[var(--muted)] hover:bg-slate-100">✕</button>
        {/* drag handle for mobile bottom sheet */}
        <div className="md:hidden mb-3 flex items-center justify-center">
          <div className="w-12 h-1.5 bg-slate-300 rounded-full" />
        </div>
        <div className="mb-3">
          <h2 className="text-lg font-semibold">Minutes</h2>
          <div className="text-xs text-[var(--muted)]">Task: {taskId}</div>
        </div>
        {/* Screen-reader live region for action feedback (polite) */}
        <div aria-live="polite" role="status" aria-atomic="true" className="sr-only">{liveMessage}</div>
        {/* Visual toast for live messages (also accessible) */}
        <Toast message={liveMessage} onClose={() => setLiveMessage(null)} />
        <div>
          {loading && <div className="p-4">Loading minutes…</div>}
          {error && <div className="p-4 text-sm text-red-600">{error}</div>}
          {text && (
            <div>
              <div className="mb-3 text-sm text-[var(--muted)]">Summary</div>
              <div className="mb-4 rounded bg-slate-50 p-3 text-sm whitespace-pre-wrap">{text.slice(0, 1000)}</div>
              <div className="mb-3 text-sm text-[var(--muted)]">Full text</div>
              <div className="mb-4 rounded bg-slate-50 p-3 text-sm whitespace-pre-wrap">{text}</div>
              <div className="mt-4">
                <div className="drawer-footer flex flex-wrap gap-2 justify-center border-t pt-3 mt-4 md:mt-6 md:border-t-0 md:pt-0" style={{ paddingBottom: 'calc(12px + env(safe-area-inset-bottom))' }}>
                  <button onClick={() => startDownload(() => fetchTranscriptDownload(taskId, 'txt'), `${taskId}_transcript.txt`, toast.addToast)} className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded bg-[var(--accent)] px-3 py-2 text-sm text-white">Download transcript</button>

                  <button onClick={() => startDownload(() => fetchSummaryDownload(taskId, 'txt'), `${taskId}_summary.txt`, toast.addToast)} className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm">Download summary</button>

                  <button onClick={() => startDownload(() => fetchActionItemsDownload(taskId, 'json'), `${taskId}_action_items.json`, toast.addToast)} className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm">Download action items</button>

                  <button onClick={async () => {
                    try { await navigator.clipboard.writeText(text); toast.addToast('Copied minutes to clipboard', { level: 'success' }) } catch { toast.addToast('Copy failed', { level: 'error' }) }
                  }} className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm">Copy</button>

                  <button onClick={handleCopyLink} className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm">Copy link</button>
                    <button onClick={handleDelete} className="flex-1 md:flex-none min-w-[44%] md:min-w-0 rounded border px-3 py-2 text-sm text-red-600 hover:bg-red-50">Delete</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </aside>
        <ConfirmDialog open={confirmOpen} title="Delete minutes" message="Delete this minutes entry? This action can be undone." onConfirm={() => { setConfirmOpen(false); handleDeleteConfirmed() }} onCancel={() => setConfirmOpen(false)} confirmLabel="Delete" cancelLabel="Cancel" />
    </div>
  )
}

import React, { useState, useEffect } from 'react'
import { Copy, Download } from 'lucide-react'
import { useToast } from './ToastProvider'
import { fetchTranscriptDownload, fetchSummaryDownload, fetchActionItemsDownload } from '../api/client'
import startDownload from '../lib/download'
import { deleteTask, undeleteTask } from '../api/client'

const Card: React.FC<{ title: string; children: React.ReactNode; onDownload?: () => void; onFocus?: () => void; onBlur?: () => void }> = ({ title, children, onDownload, onFocus, onBlur }) => (
  <div tabIndex={0} onFocus={onFocus} onBlur={onBlur} className="glass-card p-4 rounded-md mb-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--accent)] focus-visible:shadow-lg focus-visible:bg-slate-50 transform transition-transform transition-opacity duration-150 ease-out focus-visible:scale-105 focus-visible:-translate-y-1 focus-visible:opacity-100">
    <div className="flex justify-between items-start">
      <h3 id={`resultcard-${title.replace(/\s+/g, '-')}`} className="font-semibold">{title}</h3>
      <div className="flex gap-2">
        <CopyButton text={String(children)} />
        <button className="p-1 rounded hover:bg-[var(--bg-default)]" onClick={onDownload}>
          <Download size={16} />
        </button>
      </div>
    </div>
    <div className="mt-3 whitespace-pre-wrap text-sm text-[var(--muted)]">{children}</div>
  </div>
)

const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const { addToast } = useToast()
  const handle = async () => {
    try { await navigator.clipboard.writeText(text); addToast('Copied to clipboard', { level: 'success' }) } catch { addToast('Copy failed', { level: 'error' }) }
  }
  return (
    <button className="p-1 rounded hover:bg-[var(--bg-default)]" onClick={handle}>
      <Copy size={16} />
    </button>
  )
}

export default function ResultCards({ result }: { result: any | null }) {
  if (!result) return null

  const data = result.result || result
  const taskId = data.task_id || data.taskId || null

  const transcript = data.transcript || data.raw || ''
  const summary = data.summary || data.minutes || ''
  const actions = (Array.isArray(data.action_items) ? data.action_items.map((i: any) => i.text || i).join('\n') : (data.action_items && String(data.action_items))) || data.todo || ''

  const { addToast } = useToast()

  const [focusedTitle, setFocusedTitle] = useState<string | null>(null)
  const [focusedContent, setFocusedContent] = useState<string>('')

  useEffect(() => {
    // clear focused when result changes
    setFocusedTitle(null)
    setFocusedContent('')
  }, [result])

  const downloadBlob = async (fetcher: any, filename: string) => {
    if (!taskId) {
      addToast('Task id unavailable for download', { level: 'error' })
      return
    }
    await startDownload(() => fetcher(taskId), filename, addToast)
  }

  const handleMobileCopy = async () => {
    try {
      await navigator.clipboard.writeText(focusedContent)
      addToast('Copied to clipboard', { level: 'success' })
    } catch {
      addToast('Copy failed', { level: 'error' })
    }
  }

  return (
    <div>
      <Card
        title="Transcript"
        onDownload={() => downloadBlob(fetchTranscriptDownload, `minutes_${taskId || 'unknown'}_transcript.txt`)}
        onFocus={() => { setFocusedTitle('Transcript'); setFocusedContent(transcript) }}
        onBlur={() => { /* allow footer interaction */ }}
      >{transcript}</Card>

      <Card
        title="Summary"
        onDownload={() => downloadBlob(fetchSummaryDownload, `minutes_${taskId || 'unknown'}_summary.txt`)}
        onFocus={() => { setFocusedTitle('Summary'); setFocusedContent(summary) }}
      >{summary}</Card>

      <Card
        title="Action Items"
        onDownload={() => downloadBlob(fetchActionItemsDownload, `minutes_${taskId || 'unknown'}_action_items.json`)}
        onFocus={() => { setFocusedTitle('Action Items'); setFocusedContent(actions) }}
      >{actions}</Card>

      {/* Desktop: single-card delete icon in corner */}
      <div className="hidden md:flex justify-end gap-2 mt-2">
        <button onClick={async () => {
          if (!taskId) { addToast('Task id unavailable', { level: 'error' }); return }
          if (!confirm('Delete this minutes entry?')) return
          try {
            await deleteTask(taskId)
            addToast('Deleted', { level: 'success', actionLabel: 'Undo', action: async () => { try { await undeleteTask(taskId); addToast('Restored', { level: 'success' }) } catch { addToast('Restore failed', { level: 'error' }) } } })
          } catch (e) {
            addToast('Delete failed', { level: 'error' })
          }
        }} className="rounded border px-3 py-2 text-sm text-red-600 hover:bg-red-50">Delete</button>
      </div>

      {/* Mobile bottom action bar for focused card */}
      <div className={`fixed left-0 right-0 bottom-0 z-50 md:hidden transition-transform duration-200 ${focusedTitle ? 'translate-y-0' : 'translate-y-full'}`} aria-hidden={focusedTitle ? 'false' : 'true'}>
        <div className="bg-white/95 backdrop-blur-sm border-t p-3 flex items-center gap-2" style={{ paddingBottom: 'calc(12px + env(safe-area-inset-bottom))' }}>
          <div className="flex-1">
            <div className="text-sm font-medium">{focusedTitle}</div>
            <div className="text-xs text-[var(--muted)] truncate max-w-full">{focusedContent}</div>
          </div>
          <button onClick={handleMobileCopy} className="rounded bg-[var(--accent)] px-3 py-2 text-sm text-white flex items-center gap-2"><Copy size={16}/> Copy</button>
          <button onClick={() => {
            if (focusedTitle === 'Transcript') {
              downloadBlob(fetchTranscriptDownload, `minutes_${taskId || 'unknown'}_transcript.txt`)
            } else if (focusedTitle === 'Summary') {
              downloadBlob(fetchSummaryDownload, `minutes_${taskId || 'unknown'}_summary.txt`)
            } else {
              downloadBlob(fetchActionItemsDownload, `minutes_${taskId || 'unknown'}_action_items.json`)
            }
          }} className="rounded border px-3 py-2 text-sm flex items-center gap-2"><Download size={16}/> Download</button>
          <button aria-label="Close actions" onClick={() => { setFocusedTitle(null); setFocusedContent('') }} className="p-2 rounded text-[var(--muted)]">✕</button>
        </div>
      </div>
    </div>
  )
}

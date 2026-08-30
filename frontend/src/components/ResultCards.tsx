import React from 'react'
import { Copy, Download } from 'lucide-react'
import { fetchTranscriptDownload, fetchSummaryDownload, fetchActionItemsDownload } from '../api/client'

const Card: React.FC<{ title: string; children: React.ReactNode; onDownload?: () => void }> = ({ title, children, onDownload }) => (
  <div className="glass-card p-4 rounded-md mb-4">
    <div className="flex justify-between items-start">
      <h3 className="font-semibold">{title}</h3>
      <div className="flex gap-2">
        <button className="p-1 rounded hover:bg-[var(--bg-default)]" onClick={() => navigator.clipboard.writeText(String(children))}>
          <Copy size={16} />
        </button>
        <button className="p-1 rounded hover:bg-[var(--bg-default)]" onClick={onDownload}>
          <Download size={16} />
        </button>
      </div>
    </div>
    <div className="mt-3 whitespace-pre-wrap text-sm text-[var(--muted)]">{children}</div>
  </div>
)

export default function ResultCards({ result }: { result: any | null }) {
  if (!result) return null

  const data = result.result || result
  const taskId = data.task_id || data.taskId || null

  const transcript = data.transcript || data.raw || ''
  const summary = data.summary || data.minutes || ''
  const actions = (Array.isArray(data.action_items) ? data.action_items.map((i: any) => i.text || i).join('\n') : (data.action_items && String(data.action_items))) || data.todo || ''

  const downloadBlob = async (fetcher: any, filename: string) => {
    if (!taskId) {
      alert('Task id unavailable for download')
      return
    }
    try {
      const { blob, headers } = await fetcher(taskId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      alert('Download failed: ' + (e?.message || e))
    }
  }

  return (
    <div>
      <Card title="Transcript" onDownload={() => downloadBlob(fetchTranscriptDownload, `minutes_${taskId || 'unknown'}_transcript.txt`)}>{transcript}</Card>
      <Card title="Summary" onDownload={() => downloadBlob(fetchSummaryDownload, `minutes_${taskId || 'unknown'}_summary.txt`)}>{summary}</Card>
      <Card title="Action Items" onDownload={() => downloadBlob(fetchActionItemsDownload, `minutes_${taskId || 'unknown'}_action_items.json`)}>{actions}</Card>
    </div>
  )
}

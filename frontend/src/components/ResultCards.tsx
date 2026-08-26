import React from 'react'
import { Copy, Download } from 'lucide-react'

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

  const transcript = result.transcript || result.raw || ''
  const summary = result.summary || result.minutes || ''
  const actions = (result.action_items && result.action_items.join('\n')) || result.todo || ''

  return (
    <div>
      <Card title="Transcript" onDownload={() => alert('Request signed URL for transcript')}>{transcript}</Card>
      <Card title="Summary" onDownload={() => alert('Request signed URL for summary')}>{summary}</Card>
      <Card title="Action Items" onDownload={() => alert('Request signed URL for action items')}>{actions}</Card>
    </div>
  )
}

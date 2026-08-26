import React from 'react'
import { Copy, Download } from 'lucide-react'

const Card: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="glass-card p-4 rounded-md mb-4">
    <div className="flex justify-between items-start">
      <h3 className="font-semibold">{title}</h3>
      <div className="flex gap-2">
        <button className="p-1 rounded hover:bg-[var(--bg-default)]" onClick={() => navigator.clipboard.writeText(String(children))}>
          <Copy size={16} />
        </button>
        <button className="p-1 rounded hover:bg-[var(--bg-default)]" onClick={() => alert('Trigger download via backend signed URL')}>
          <Download size={16} />
        </button>
      </div>
    </div>
    <div className="mt-3 text-sm text-[var(--muted)]">{children}</div>
  </div>
)

export default function ResultCards() {
  return (
    <div>
      <Card title="Transcript">Full transcript goes here. Lorem ipsum...</Card>
      <Card title="Summary">Summary text goes here. Short summary...</Card>
      <Card title="Action Items">- Follow up on X\n- Share with team</Card>
    </div>
  )
}

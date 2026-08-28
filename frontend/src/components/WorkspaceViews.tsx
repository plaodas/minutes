import React, { useState } from 'react'
import { ChevronRight, Clock3, FileAudio, Plus, SlidersHorizontal } from 'lucide-react'

const sampleMinutes = [
  { name: 'Product planning.mp3', date: 'Today, 09:42', duration: '42 min', status: 'Ready' },
  { name: 'Design review.wav', date: 'Yesterday, 16:10', duration: '28 min', status: 'Ready' },
  { name: 'Weekly sync.mp3', date: 'Aug 26, 11:00', duration: '35 min', status: 'Ready' },
]

export function HistoryView({ onCreate }: { onCreate: () => void }) {
  return (
    <section>
      <div className="mb-7 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[var(--accent)]">Workspace archive</p>
          <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Recent minutes</h1>
        </div>
        <button type="button" onClick={onCreate} className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white shadow-sm hover:brightness-95">
          <Plus size={17} /> New upload
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        {sampleMinutes.map((item) => (
          <button key={item.name} type="button" className="flex w-full items-center gap-3 border-b border-slate-100 p-4 text-left last:border-0 hover:bg-slate-50">
            <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]"><FileAudio size={20} /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{item.name}</span>
              <span className="mt-1 flex items-center gap-1 text-xs text-[var(--muted)]"><Clock3 size={13} /> {item.date} · {item.duration}</span>
            </span>
            <span className="hidden rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 sm:inline">{item.status}</span>
            <ChevronRight className="shrink-0 text-slate-400" size={18} />
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">Sample records are shown until the history API is connected.</p>
    </section>
  )
}

export function SettingsView() {
  const [includeActions, setIncludeActions] = useState(true)
  const [language, setLanguage] = useState('Japanese')

  return (
    <section>
      <div className="mb-7">
        <p className="text-sm font-medium text-[var(--accent)]">Preferences</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Settings</h1>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex items-start gap-3 border-b border-slate-100 p-4">
          <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]"><SlidersHorizontal size={20} /></span>
          <div className="min-w-0 flex-1">
            <label htmlFor="language" className="block text-sm font-medium">Transcript language</label>
            <select id="language" value={language} onChange={(event) => setLanguage(event.target.value)} className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm sm:max-w-xs">
              <option>Japanese</option>
              <option>English</option>
              <option>Auto-detect</option>
            </select>
          </div>
        </div>
        <label className="flex cursor-pointer items-center justify-between gap-5 p-4">
          <span><span className="block text-sm font-medium">Include action items</span><span className="mt-1 block text-sm text-[var(--muted)]">Extract tasks and owners from the meeting.</span></span>
          <input type="checkbox" checked={includeActions} onChange={(event) => setIncludeActions(event.target.checked)} className="h-5 w-5 shrink-0 accent-[var(--accent)]" />
        </label>
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">Settings are local UI controls; persistence will be added with the settings API.</p>
    </section>
  )
}

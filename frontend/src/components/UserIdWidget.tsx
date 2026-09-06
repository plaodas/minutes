import React from 'react'
import useLocalStorage from '../hooks/useLocalStorage'

function generateUuid() {
  try {
    return (window as any).crypto?.randomUUID?.() || ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, (c:any) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16))
  } catch (e) {
    // fallback simple UUID-ish
    return 'id-' + Math.random().toString(36).slice(2, 10)
  }
}

export default function UserIdWidget() {
  const [userId, setUserId] = useLocalStorage<string | null>('minutes.userId', null)

  const ensureId = () => {
    if (!userId) setUserId(generateUuid())
  }

  const regenerate = () => {
    const id = generateUuid()
    setUserId(id)
  }

  const clear = () => setUserId(null)

  const copy = async () => {
    try {
      if (userId) await navigator.clipboard.writeText(userId)
      // optionally show feedback (not implemented)
    } catch (e) {
      // ignore
    }
  }

  return (
    <div className="border-b border-slate-100 p-4">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <label className="block text-sm font-medium">Current User ID</label>
          <div className="mt-2 flex items-center gap-2">
            <div className="truncate rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">{userId || <span className="text-[var(--muted)]">(not set)</span>}</div>
            <button onClick={() => { ensureId() }} className="rounded bg-[var(--accent)] px-3 py-1 text-sm text-white">Generate</button>
            <button onClick={() => regenerate()} className="rounded bg-slate-100 px-3 py-1 text-sm">Regenerate</button>
            <button onClick={() => copy()} className="rounded bg-slate-100 px-3 py-1 text-sm">Copy</button>
            <button onClick={() => clear()} className="rounded bg-rose-100 px-3 py-1 text-sm text-rose-700">Clear</button>
          </div>
        </div>
      </div>
      <p className="mt-2 text-xs text-[var(--muted)]">This ID is stored locally and used to attribute uploads.</p>
    </div>
  )
}

import React, { useState, useEffect } from 'react'
import { ChevronRight, Clock3, FileAudio, Plus, SlidersHorizontal } from 'lucide-react'

const sampleMinutes = [
  { name: 'Product planning.mp3', date: 'Today, 09:42', duration: '42 min', status: 'Ready', id: 'sample-1', created_at: new Date().toISOString() },
  { name: 'Design review.wav', date: 'Yesterday, 16:10', duration: '28 min', status: 'Ready', id: 'sample-2', created_at: new Date(Date.now() - 86400000).toISOString() },
  { name: 'Weekly sync.mp3', date: 'Aug 26, 11:00', duration: '35 min', status: 'Ready', id: 'sample-3', created_at: new Date(Date.now() - 7 * 86400000).toISOString() },
]

export function HistoryView({ onCreate }: { onCreate: () => void }) {
  const [items, setItems] = useState<Array<any>>([])
  const [loading, setLoading] = useState(false)
  const [visibleCount, setVisibleCount] = useState<number>(5)
  const [modalTask, setModalTask] = useState<string | null>(null)
  const [isModalVisible, setIsModalVisible] = useState(false)
  const prevFocusRef = React.useRef<HTMLElement | null>(null)
  const listRef = React.useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const raw = localStorage.getItem('recent_tasks')
    let arr = raw ? JSON.parse(raw) : sampleMinutes
    if (!Array.isArray(arr)) arr = sampleMinutes
    setItems(arr)
    // set items first, then fetch histories only for visible items (avoid fetching all at once)
    const fetchForVisible = async () => {
      const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
      setLoading(true)
      try {
        const limit = Number(import.meta.env.VITE_BG_HISTORY_INITIAL_LIMIT || 5)
        const ids = arr.slice(0, visibleCount).map((it: any) => it.id).filter(Boolean)
        if (ids.length === 0) return
        const res = await fetch(`${BASE}/bg/histories`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids, limit, offset: 0 }),
        })
        if (!res.ok) return
        const j = await res.json()
        const map = j.histories || {}
        const merged = arr.map((it: any) => ({ ...it, histories: map[it.id] || [] }))
        setItems(merged)
      } catch (e) {
        // ignore
      } finally {
        setLoading(false)
      }
    }

    fetchForVisible()
  }, [])

  // when visibleCount increases, fetch histories for newly visible items that don't have histories yet
  useEffect(() => {
    const idsToFetch = items.slice(0, visibleCount).filter((it: any) => !it.histories || it.histories.length === 0).map((it: any) => it.id)
    if (idsToFetch.length === 0) return
    const fetchChunk = async (ids: string[]) => {
      const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
      try {
        const limit = Number(import.meta.env.VITE_BG_HISTORY_INITIAL_LIMIT || 5)
        const res = await fetch(`${BASE}/bg/histories`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids, limit, offset: 0 }),
        })
        if (!res.ok) return
        const j = await res.json()
        const map = j.histories || {}
        setItems((prev) => prev.map((it) => ({ ...it, histories: it.histories && it.histories.length ? it.histories : map[it.id] || [] })))
      } catch (e) {
        // ignore
      }
    }

    // chunk ids to avoid long lists
    const CHUNK = 25
    for (let i = 0; i < idsToFetch.length; i += CHUNK) {
      fetchChunk(idsToFetch.slice(i, i + CHUNK))
    }
  }, [visibleCount, items])

  // manage body scroll while modalTask is set
  useEffect(() => {
    if (modalTask) {
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [modalTask])

  const openModal = (id: string) => {
    prevFocusRef.current = document.activeElement as HTMLElement | null
    setModalTask(id)
    // allow mount, then trigger visible for animation
    setTimeout(() => setIsModalVisible(true), 10)
  }

  const closeModal = () => {
    setIsModalVisible(false)
    // wait for animation to finish then unmount
    setTimeout(() => {
      setModalTask(null)
      // return focus to previous element
      try { prevFocusRef.current?.focus() } catch {}
    }, 220)
  }

  // focus trap and ESC handling when modal is open
  useEffect(() => {
    if (!modalTask) return
    const root = document.querySelector('[role="dialog"]') as HTMLElement | null
    const getFocusable = () => {
      if (!root) return [] as HTMLElement[]
      const selector = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
      return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter((el) => !el.hasAttribute('disabled'))
    }
    const focusables = getFocusable()
    // focus first focusable element
    setTimeout(() => { focusables[0]?.focus() }, 20)

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault(); closeModal(); return
      }
      if (e.key !== 'Tab') return
      const list = getFocusable()
      if (list.length === 0) {
        e.preventDefault(); return
      }
      const idx = list.indexOf(document.activeElement as HTMLElement)
      if (e.shiftKey) {
        if (idx <= 0) {
          e.preventDefault(); list[list.length - 1].focus()
        }
      } else {
        if (idx === list.length - 1) {
          e.preventDefault(); list[0].focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [modalTask])

  // infinite scroll: observe sentinel and load more items
  useEffect(() => {
    const sentinel = document.querySelector('[data-testid="history-list-sentinel"]') as HTMLElement | null
    if (!sentinel) return
    // only observe when there are more items to load
    if (items.length <= visibleCount) return
    // use viewport as root so page scrolling triggers loading
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          setVisibleCount((v) => Math.min(items.length, v + 5))
        }
      }
    }, { root: null, rootMargin: '200px' })
    obs.observe(sentinel)
    return () => obs.disconnect()
  }, [items, visibleCount])

  return (
    <>
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

        <div ref={listRef} className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          {items.length === 0 && (
            <div className="p-6 text-sm text-[var(--muted)]">No recent tasks. Upload audio to see history here.</div>
          )}

          {items.slice(0, visibleCount).map((item) => (
            <div key={item.id} className="flex w-full items-center gap-3 border-b border-slate-100 p-4 text-left last:border-0 hover:bg-slate-50">
              <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]"><FileAudio size={20} /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{item.name}</span>
                <span className="mt-1 flex items-center gap-1 text-xs text-[var(--muted)]"><Clock3 size={13} /> {item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>

                {item.histories && item.histories.length > 0 && (
                  <div className="mt-1 text-xs text-[var(--muted)]">
                    {item.histories.slice(0, 5).map((h: any, idx: number) => (
                      <div key={idx} className="truncate">
                        {h.event_ts ? new Date(h.event_ts).toLocaleString() + ' — ' : ''}
                        <strong>{h.event_type}</strong>
                        {h.payload?.error ? ` — ${h.payload.error}` : ''}
                      </div>
                    ))}
                    {item.histories.length === 0 && <div>—</div>}
                      <div className="mt-2 flex items-center gap-2">
                          <button data-testid={`view-history-${item.id}`} type="button" onClick={() => openModal(item.id)} className="text-xs text-[var(--accent)]">View full history</button>
                        <span className="text-xs text-[var(--muted)]">Showing {item.histories.length}</span>
                      </div>
                  </div>
                )}
              </span>

              <span className="hidden rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 sm:inline">{item.latest ? item.latest.event_type : '—'}</span>
              <ChevronRight className="shrink-0 text-slate-400" size={18} />
            </div>
          ))}
          {/* sentinel for infinite scroll */}
          <div aria-hidden="true" data-testid="history-list-sentinel" />
        </div>

        <p className="mt-3 text-xs text-[var(--muted)]">{loading ? 'Loading history...' : 'History is loaded from the backend.'}</p>
      </section>

      {modalTask && (
        <div onClick={(e) => { if (e.target === e.currentTarget) closeModal() }} className={`fixed inset-0 z-50 flex items-start justify-center p-6 transition-opacity duration-200 ${isModalVisible ? 'bg-black/40 opacity-100' : 'bg-black/0 opacity-0'}`}>
          <div role="dialog" aria-modal="true" aria-label={`Full history for ${modalTask}`} className={`relative max-h-[80vh] w-full max-w-2xl overflow-auto rounded bg-white p-6 transform transition-all duration-200 ${isModalVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'}`}>
            <button aria-label="Close" onClick={() => closeModal()} className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-[var(--muted)] hover:bg-slate-100">✕</button>
            <div className="mb-4">
              <h2 className="text-lg font-semibold">Full history for {modalTask}</h2>
            </div>
            <div>
              {(items.find((it) => it.id === modalTask)?.histories || []).map((h: any, idx: number) => (
                <div key={idx} className="mb-4 border-b pb-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-[var(--muted)]">{h.event_ts ? new Date(h.event_ts).toLocaleString() : ''}</div>
                    <div className="text-sm font-medium">{h.event_type}</div>
                  </div>
                  <div className="mt-2 text-xs">
                    <pre className="rounded bg-slate-50 p-2 text-xs">{JSON.stringify(h.payload, null, 2)}</pre>
                    {h.payload?.result?.output_file && (
                      <div className="mt-2 text-sm"><a target="_blank" rel="noreferrer" href={(import.meta.env.VITE_API_BASE || 'http://localhost:8000') + '/' + h.payload.result.output_file}>Open output file</a></div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
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

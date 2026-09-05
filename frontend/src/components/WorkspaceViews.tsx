import React, { useState, useEffect } from 'react'
import fetchWithRetry from '../lib/fetchWithRetry'
import { MinutesDrawer } from './MinutesDrawer'
import { ChevronRight, Clock3, FileAudio, Plus, SlidersHorizontal } from 'lucide-react'
import { useTasks } from '../hooks/useTasks'

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
  const [minutesTask, setMinutesTask] = useState<string | null>(null)
  const [isMinutesVisible, setIsMinutesVisible] = useState(false)
  const [loadingPerTask, setLoadingPerTask] = useState<Record<string, boolean>>({})
  const [hasMorePerTask, setHasMorePerTask] = useState<Record<string, boolean>>({})
  const [hasMore, setHasMore] = useState<boolean>(true)
  const [loadingMore, setLoadingMore] = useState<boolean>(false)
  const prevFocusRef = React.useRef<HTMLElement | null>(null)
  const listRef = React.useRef<HTMLDivElement | null>(null)

  // useTasks provides initial fetch + cache + retry UI
  const { tasks, loading: tasksLoading, error: tasksError, reload } = useTasks()

  useEffect(() => {
    setLoading(tasksLoading)
  }, [tasksLoading])

  useEffect(() => {
    if (tasks && Array.isArray(tasks)) {
      // map server shape to local UI shape if necessary
      const arr = tasks.map((t: any) => ({
        id: t.id,
        name: t.name || t.result?.upload_filename || `task-${String(t.id).slice(0, 8)}`,
        created_at: t.created_at,
        status: t.status,
        progress: t.progress,
        result: t.result,
        histories: (t.preview_events || t.histories || []).slice(0, 3),
        event_count: t.event_count || 0,
      }))
      setItems(arr)
      // heuristics: if tasks length < page limit, assume no more
      const limit = Number(import.meta.env.VITE_TASKS_PAGE_LIMIT || 20)
      setHasMore(arr.length >= limit)
    }
  }, [tasks])

  // when visibleCount increases, fetch histories for newly visible items that don't have histories yet
  // No incremental per-task preview loading: server provides `preview_events` on /bg/tasks.

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
    // fetch full events for this task once (modal will display full events)
    ;(async () => {
      const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
      try {
        setLoadingPerTask((s) => ({ ...s, [id]: true }))
        const res = await fetch(`${BASE}/bg/tasks/${id}/events`)
        if (res.ok) {
          const j = await res.json()
          const ev = j.events || []
          setItems((prev) => prev.map((it) => it.id === id ? ({ ...it, histories: ev }) : it))
          setHasMorePerTask((s) => ({ ...s, [id]: false }))
        }
      } catch (e) {
        // ignore
      } finally {
        setLoadingPerTask((s) => ({ ...s, [id]: false }))
      }
    })()
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
    // focus close button (if present) to make focus behavior deterministic
    setTimeout(() => {
      const closeBtn = document.querySelector('[role="dialog"] button[aria-label="Close"]') as HTMLElement | null
      if (closeBtn) {
        try { closeBtn.focus() } catch {}
        return
      }
      const focusables = getFocusable()
      focusables[0]?.focus()
    }, 50)

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
  // infinite scroll: when sentinel visible, fetch next page from server if available
  useEffect(() => {
    const sentinel = document.querySelector('[data-testid="history-list-sentinel"]') as HTMLElement | null
    if (!sentinel) return
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          // load next page
          if (loadingMore || !hasMore) return
          setLoadingMore(true)
                ;(async () => {
                  try {
                    const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
                    const limit = Number(import.meta.env.VITE_TASKS_PAGE_LIMIT || 20)
                    const offset = items.length
                    // If offset is 0 the initial page is already loaded via `useTasks`.
                    // Avoid fetching page 0 again which causes duplicate items.
                    if (offset === 0) {
                      return
                    }
                    const res = await fetchWithRetry(`${BASE}/bg/tasks?limit=${limit}&offset=${offset}`)
              const j = await res.json()
              const arr = (j.tasks || []).map((t: any) => ({
                id: t.id,
                name: t.name || t.result?.upload_filename || `task-${String(t.id).slice(0, 8)}`,
                created_at: t.created_at,
                status: t.status,
                progress: t.progress,
                result: t.result,
                histories: (t.preview_events || []).slice(0, 3),
                event_count: t.event_count || 0,
              }))
              setItems((prev) => [...prev, ...arr])
              setHasMore(arr.length >= limit)
            } catch (err) {
              // ignore load-more errors; user can retry via page refresh or reload button
            } finally {
              setLoadingMore(false)
            }
          })()
        }
      }
    }, { root: null, rootMargin: '200px' })
    obs.observe(sentinel)
    return () => obs.disconnect()
  }, [items, hasMore, loadingMore])

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

        {/* Inline error/banner when tasks fetch fails */}
        {tasksError && (
          <div className={`mb-4 rounded-md p-3 border ${items && items.length > 0 ? 'bg-yellow-50 border-yellow-200' : 'bg-rose-50 border-rose-200'}`}>
            <div className="flex items-center justify-between gap-4">
              <div className="text-sm">
              {items && items.length > 0 ? (
                <span>Could not retrieve the latest history. Displaying older data.</span>
              ) : (
                <span>Failed to load history. Please check your network connection.</span>
              )}
              </div>
              <div className="shrink-0">
                <button onClick={() => reload()} className={`rounded px-3 py-1 text-sm font-medium text-white ${items && items.length > 0 ? 'bg-yellow-600 hover:brightness-90' : 'bg-rose-600 hover:brightness-90'}`}>Retry</button>
              </div>
            </div>
          </div>
        )}


        <div ref={listRef} className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          {items.length === 0 && (
            <div className="p-6 text-sm text-[var(--muted)]">No recent tasks. Upload audio to see history here.</div>
          )}

          {items.map((item) => (
            <div key={item.id} data-testid={`view-minutes-${item.id}`} role="button" tabIndex={0} aria-labelledby={`history-title-${item.id}`} aria-describedby={`history-desc-${item.id}`} onClick={() => { setMinutesTask(item.id); setIsMinutesVisible(true) }} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setMinutesTask(item.id); setIsMinutesVisible(true) } }} className="cursor-pointer flex w-full items-center gap-3 border-b border-slate-100 p-4 text-left last:border-0 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--accent)] focus-visible:shadow-lg focus-visible:bg-slate-50 transform transition-transform transition-opacity duration-150 ease-out focus-visible:scale-105 focus-visible:-translate-y-1 focus-visible:opacity-100">
              <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]"><FileAudio size={20} /></span>
              <span className="min-w-0 flex-1">
                <span id={`history-title-${item.id}`} className="block truncate text-sm font-medium">{item.name}</span>
                <span id={`history-desc-${item.id}`} className="sr-only">{item.created_at ? new Date(item.created_at).toLocaleString() + ', ' : ''}{item.status || 'Status unknown'}</span>
                <span className="mt-1 flex items-center gap-1 text-xs text-[var(--muted)]"><Clock3 size={13} /> {item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>

                <div className="mt-1 text-xs text-[var(--muted)]">
                  {item.histories && item.histories.length > 0 ? (
                    item.histories.slice(0, 3).map((h: any, idx: number) => (
                      <div key={idx} className="truncate">
                        {h.event_ts ? new Date(h.event_ts).toLocaleString() + ' — ' : ''}
                        <strong>{h.event_type}</strong>
                        {h.payload?.error ? ` — ${h.payload.error}` : ''}
                      </div>
                    ))
                  ) : (
                    <div>—</div>
                  )}
                  <div className="mt-2 flex items-center gap-2">
                    <button data-testid={`view-history-${item.id}`} type="button" onClick={(e) => { e.stopPropagation(); openModal(item.id) }} className="text-xs text-[var(--accent)]">View full events</button>
                    <span className="text-xs text-[var(--muted)]">Showing {item.histories ? item.histories.length : 0}{item.event_count ? ` of ${item.event_count}` : ''}</span>
                  </div>
                </div>
              </span>

              <span className="hidden rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 sm:inline">{item.latest ? item.latest.event_type : '—'}</span>
              <button aria-label={`View minutes for ${item.name || item.id}`} onClick={(e) => { e.stopPropagation(); setMinutesTask(item.id); setIsMinutesVisible(true) }} className="shrink-0 text-slate-400 rounded hover:bg-slate-100 p-1">
                <ChevronRight size={18} />
              </button>
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
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Full history for {items.find((it) => it.id === modalTask)?.name || modalTask}</h2>
              <div>
                <button data-testid={`rename-${modalTask}`} onClick={async () => {
                  const newName = window.prompt('Enter new name for this task', items.find((it) => it.id === modalTask)?.name || '')
                  if (!newName) return
                    try {
                      const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
                      // use fetchWithRetry but with zero retries to get timeout/abort behavior without unsafe POST retries
                      const res = await fetchWithRetry(`${BASE}/bg/task/${modalTask}/rename`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName })
                      }, { retries: 0, timeoutMs: 10000 })
                      if (res.ok) {
                        setItems((prev) => prev.map((it) => it.id === modalTask ? ({ ...it, name: newName }) : it))
                      }
                    } catch (e) {
                      // ignore
                    }
                }} className="mr-3 rounded bg-slate-100 px-2 py-1 text-sm">Rename</button>
              </div>
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
                    <div className="mt-4">
                      <div className="text-sm text-[var(--muted)]">All events loaded</div>
                    </div>
            </div>
          </div>
        </div>
      )}
        {/* Minutes drawer */}
        {minutesTask && isMinutesVisible && (
          <MinutesDrawer taskId={minutesTask} onClose={() => { setIsMinutesVisible(false); setMinutesTask(null) }} />
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

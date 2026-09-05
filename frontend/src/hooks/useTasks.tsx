import { useCallback, useEffect, useState } from 'react'
import fetchWithRetry from '../lib/fetchWithRetry'
import { useToast } from '../components/ToastProvider'

type TaskItem = any

export function useTasks() {
  const [tasks, setTasks] = useState<TaskItem[] | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<any>(null)
  const { addToast } = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
      const res = await fetchWithRetry(`${BASE}/bg/tasks`, { credentials: 'same-origin' }, { retries: 3, timeoutMs: 10000 })
      const data = await res.json()
      const payload = (data && data.tasks) ? data.tasks : data
      setTasks(payload)
      try {
        localStorage.setItem('cached_tasks', JSON.stringify(payload))
      } catch (e) {
        // ignore
      }
    } catch (e: any) {
      setError(e)
      // Try cached fallback
        try {
          const cached = localStorage.getItem('cached_tasks')
          if (cached) {
            const parsed = JSON.parse(cached)
            setTasks(parsed && parsed.tasks ? parsed.tasks : parsed)
          }
        } catch (err) {
          // ignore
        }

      addToast('Failed to load history', {
        level: 'error',
        actionLabel: 'Retry',
        action: () => {
          load()
        }
      })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    load()
    const onTaskChanged = () => load()
    window.addEventListener('app:task-changed', onTaskChanged)
    const onOnline = () => load()
    window.addEventListener('online', onOnline)
    // Subscribe to server-sent events for live task updates
    const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000')
    let es: EventSource | null = null
    try {
      if (typeof window !== 'undefined' && (window as any).EventSource) {
        es = new EventSource(`${BASE}/bg/events`)
        es.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data)
            // merge update into tasks list when available
            setTasks((prev) => {
              if (!prev) return prev
              const id = data.task_id
              const idx = prev.findIndex((t: any) => String(t.id) === String(id))
              if (idx === -1) {
                // unknown task — reload full list asynchronously
                setTimeout(() => {
                  load()
                }, 0)
                return prev
              }
              const copy = prev.slice()
              const item = Object.assign({}, copy[idx])
              // apply common event types
              if (data.event_type === 'progress' && data.payload && typeof data.payload.progress !== 'undefined') {
                item.progress = Number(data.payload.progress)
              }
              if (data.event_type === 'status' && data.payload && data.payload.status) {
                item.status = data.payload.status
              }
              if (data.event_type === 'success') {
                item.status = 'success'
                item.progress = 100.0
                if (data.payload && data.payload.result) {
                  item.result = data.payload.result
                }
              }
              copy[idx] = item
              return copy
            })
          } catch (err) {
            // ignore malformed events
          }
        }
        es.onerror = () => {
          // EventSource will auto-reconnect; nothing to do here
        }
      }
    } catch (err) {
      // ignore EventSource errors
    }
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('app:task-changed', onTaskChanged)
      try {
        if (es) es.close()
      } catch (e) {}
    }
  }, [load])

  return { tasks, loading, error, reload: load }
}

export default useTasks

import { useCallback, useEffect, useState } from 'react'
import fetchWithRetry from '../lib/fetchWithRetry'
import { useToast } from '../components/ToastProvider'
import { useTaskEvents } from '../events/TaskEventsProvider'

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
      const BASE = (import.meta.env.VITE_API_BASE || '/api')
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

  useTaskEvents((data) => {
    setTasks((prev) => {
      if (!prev) return prev
      const id = data.task_id
      const idx = prev.findIndex((task: any) => String(task.id) === String(id))
      if (idx === -1) {
        setTimeout(() => load(), 0)
        return prev
      }
      const copy = prev.slice()
      const item = Object.assign({}, copy[idx])
      if (data.event_type === 'progress') {
        item.progress = data.payload.progress
      }
      if (data.event_type === 'status') {
        item.status = data.payload.status
        item.stage = data.stage
      }
      if (data.event_type === 'success') {
        item.status = 'success'
        item.stage = data.stage ?? 'success'
        item.progress = 100.0
        if (data.payload.result) {
          item.result = data.payload.result
        }
        setTimeout(() => load(), 0)
      }
      copy[idx] = item
      return copy
    })
  })

  useEffect(() => {
    load()
    const onTaskChanged = () => load()
    window.addEventListener('app:task-changed', onTaskChanged)
    const onOnline = () => load()
    window.addEventListener('online', onOnline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('app:task-changed', onTaskChanged)
    }
  }, [load])

  return { tasks, loading, error, reload: load }
}

export default useTasks

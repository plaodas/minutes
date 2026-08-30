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
      setTasks(data)
      try {
        localStorage.setItem('cached_tasks', JSON.stringify(data))
      } catch (e) {
        // ignore
      }
    } catch (e: any) {
      setError(e)
      // Try cached fallback
      try {
        const cached = localStorage.getItem('cached_tasks')
        if (cached) setTasks(JSON.parse(cached))
      } catch (err) {
        // ignore
      }

      addToast('履歴の読み込みに失敗しました', {
        level: 'error',
        actionLabel: '再試行',
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
    const onOnline = () => load()
    window.addEventListener('online', onOnline)
    return () => window.removeEventListener('online', onOnline)
  }, [load])

  return { tasks, loading, error, reload: load }
}

export default useTasks

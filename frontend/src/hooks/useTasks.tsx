import { useCallback, useEffect, useState } from 'react'
import { getBgTasks } from '../api/client'
import { applyTaskEvent, parseTaskListResponse } from '../lib/taskState'
import type { TaskListItem } from '../lib/taskState'
import { useToast } from '../components/ToastProvider'
import { useTaskEvents } from '../events/TaskEventsProvider'

export function useTasks() {
  const [tasks, setTasks] = useState<TaskListItem[] | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<any>(null)
  const { addToast } = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const nextTasks = await getBgTasks()
      setTasks(nextTasks)
      try {
        localStorage.setItem('cached_tasks', JSON.stringify(nextTasks))
      } catch (e) {
        // ignore
      }
    } catch (e: any) {
      setError(e)
      // Try cached fallback
        try {
          const cached = localStorage.getItem('cached_tasks')
          if (cached) {
            const parsed = parseTaskListResponse(JSON.parse(cached))
            if (parsed) setTasks(parsed)
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
      const result = applyTaskEvent(prev, data)
      if (result.shouldReload) setTimeout(() => load(), 0)
      return result.tasks
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

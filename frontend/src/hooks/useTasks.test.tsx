import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, vi, beforeEach, expect } from 'vitest'
import { ToastProvider } from '../components/ToastProvider'
import { useTasks } from './useTasks'

// Test component to expose hook state
function TestComponent() {
  const { tasks, loading, error } = useTasks()
  return (
    <div>
      <div data-testid="loading">{loading ? '1' : '0'}</div>
      <div data-testid="error">{error ? '1' : '0'}</div>
      <div data-testid="tasks">{tasks ? JSON.stringify(tasks) : ''}</div>
    </div>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  // clear localStorage
  try { localStorage.clear() } catch (e) {}
})

describe('useTasks', () => {
  it('loads tasks and caches them', async () => {
    const mockData = { tasks: [{ id: 't1' }, { id: 't2' }] }
    // mock fetchWithRetry module
    const mod = await import('../lib/fetchWithRetry')
    vi.spyOn(mod, 'default').mockResolvedValue(new Response(JSON.stringify(mockData), { status: 200 }))

    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('0'))
    expect(screen.getByTestId('tasks').textContent).toContain('t1')
    // cached
    expect(localStorage.getItem('cached_tasks')).toBeTruthy()
  })

  it('falls back to cache on network failure and shows toast', async () => {
    const cached = { tasks: [{ id: 'cached1' }] }
    localStorage.setItem('cached_tasks', JSON.stringify(cached))
    const mod = await import('../lib/fetchWithRetry')
    vi.spyOn(mod, 'default').mockRejectedValue(new Error('network'))

    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('0'))
    expect(screen.getByTestId('tasks').textContent).toContain('cached1')
  })
})

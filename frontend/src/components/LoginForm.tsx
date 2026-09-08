import React, { useState } from 'react'
import { login, logout, getUserFeatures } from '../api/client'
import { useToast } from './ToastProvider'

export default function LoginForm() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { addToast } = useToast()

  const doLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await login(username, password)
      addToast('Login successful', { level: 'success' })
      // notify app about auth change so UI can refresh without full reload
      try { window.dispatchEvent(new CustomEvent('auth-changed')) } catch (e) {}
    } catch (err: any) {
      addToast(err?.message || 'Login failed', { level: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const doLogout = async () => {
    setLoading(true)
    try {
      await logout()
      addToast('Logged out', { level: 'success' })
      try { window.dispatchEvent(new CustomEvent('auth-changed')) } catch (e) {}
    } catch (err: any) {
      addToast(err?.message || 'Logout failed', { level: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border-b border-slate-100 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Authentication</p>
          <p className="mt-1 text-xs text-[var(--muted)]">Sign in to access admin features and manage buckets.</p>
        </div>
      </div>
      <form onSubmit={doLogin} className="mt-3 flex flex-col gap-2">
        <input aria-label="username" placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded border px-3 py-2 text-sm" />
        <input aria-label="password" placeholder="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded border px-3 py-2 text-sm" />
        <div className="flex items-center gap-2 justify-end">
          <button type="submit" disabled={loading} className="rounded bg-[var(--accent)] px-3 py-2 text-sm text-white">Sign in</button>
          <button type="button" onClick={doLogout} disabled={loading} className="rounded bg-slate-100 px-3 py-2 text-sm">Sign out</button>
        </div>
      </form>
    </div>
  )
}

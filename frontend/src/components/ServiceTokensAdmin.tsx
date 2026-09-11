import React, { useEffect, useState } from 'react'
import { listServiceTokens, createServiceToken, revokeServiceToken } from '../api/client'
import { useToast } from './ToastProvider'
import ConfirmModal from './ConfirmModal'

export default function ServiceTokensAdmin() {
  const [tokens, setTokens] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [name, setName] = useState('')
  const [userId, setUserId] = useState('')
  const { addToast } = useToast()
  // confirm modal for revocation
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmMessage, setConfirmMessage] = useState('')
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listServiceTokens()
      setTokens((data && data.tokens) || [])
    } catch (e: any) {
      addToast(e.message || 'failed to load tokens', { level: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const data = await createServiceToken(name || undefined, userId || undefined)
      // data contains plaintext token and id
      addToast('Token created — copy it now (shown once)', { level: 'success' })
      // show token in prompt for quick copy
      try { window.prompt('Service token (copy and store securely):', data.token) } catch {}
      setName('')
      setUserId('')
      await load()
    } catch (e: any) {
      addToast(e.message || 'create failed', { level: 'error' })
    }
  }

  const handleRevoke = async (id: string) => {
    // open confirmation modal instead of native confirm
    setConfirmMessage('Revoke this token?')
    setConfirmAction(() => async () => {
      setConfirmOpen(false)
      try {
        await revokeServiceToken(id)
        addToast('Token revoked', { level: 'success' })
        await load()
      } catch (e: any) {
        addToast(e.message || 'revoke failed', { level: 'error' })
      }
    })
    setConfirmOpen(true)
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Service tokens</h2>
        <p className="text-sm text-[var(--muted)]">Create and revoke service tokens for programmatic access.</p>
      </div>

      <form onSubmit={handleCreate} className="mb-4 flex flex-col sm:flex-row gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="token name (optional)" className="rounded border px-2 py-1" />
        <input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="associate user id (optional)" className="rounded border px-2 py-1" />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" type="submit">Create token</button>
      </form>

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">Loading…</div>
        ) : (
          <ul className="space-y-2">
            {tokens.map((t: any) => (
              <li key={t.id} className="rounded border p-2 flex items-center justify-between">
                <div>
                  <div className="font-medium">{t.name || t.id}</div>
                  <div className="text-xs text-[var(--muted)]">user: {t.user_id || '—'}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => { try { window.prompt('Token id:', t.id) } catch {} }} className="rounded bg-slate-100 px-2 py-1 text-sm">Show id</button>
                  <button onClick={() => handleRevoke(t.id)} className="rounded bg-red-600 px-2 py-1 text-sm text-white">Revoke</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmModal
        open={confirmOpen}
        title="Confirm"
        message={confirmMessage}
        confirmLabel="Revoke"
        cancelLabel="Cancel"
        onConfirm={() => { if (confirmAction) confirmAction() }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}

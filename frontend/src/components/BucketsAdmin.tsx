import React, { useEffect, useState } from 'react'
import { getBuckets, createBucket } from '../api/client'
import UserIdWidget from './UserIdWidget'

// BucketsAdmin also hosts other admin tools (service tokens, user id helper)

export default function BucketsAdmin() {
  const [buckets, setBuckets] = useState<any[]>([])
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
    const data = await getBuckets()
    setBuckets((data && data.buckets) || [])
    } catch (e: any) {
      setError(e.message || 'failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const [features, setFeatures] = useState<{ authenticated?: boolean } | null>(null)
  useEffect(() => {
    let mounted = true
    import('../api/client').then(({ getUserFeatures }) => {
      getUserFeatures().then((f) => { if (mounted) setFeatures(f) }).catch(() => { if (mounted) setFeatures({ authenticated: false }) })
    })
    return () => { mounted = false }
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await createBucket(name)
      setName('')
      await load()
    } catch (e: any) {
      setError(e.message || 'create failed')
    }
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Admin Tools</h2>
        <p className="text-sm text-[var(--muted)]">Manage buckets, service tokens, and admin helpers.</p>
      </div>

      {(!features || features.authenticated === false) && <div className="mb-4"><UserIdWidget /></div>}

      <form onSubmit={handleCreate} className="mb-4 flex gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="bucket-name" className="rounded border px-2 py-1" />
        <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" disabled={!name}>Create</button>
      </form>

      {error && <div className="mb-2 text-sm text-red-600">{error}</div>}

      <div>
        {loading ? (
          <div className="text-sm text-[var(--muted)]">Loading…</div>
        ) : (
          <ul className="space-y-2">
            {buckets.map((b: any) => (
              <li key={b.id} className="rounded border p-2">
                <div className="font-medium">{b.name}</div>
                <div className="text-xs text-[var(--muted)]">owner: {b.owner_id || '—'}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { getBuckets, createBucket, adminUploadsCleanupGet, adminUploadsCleanupPost } from '../api/client'
import ConfirmModal from './ConfirmModal'

// BucketsAdmin also hosts other admin tools (service tokens, user id helper)

export default function BucketsAdmin() {
  const [buckets, setBuckets] = useState<any[]>([])
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // uploads cleanup UI state
  const [uploadsDir, setUploadsDir] = useState('')
  const [uploadsPattern, setUploadsPattern] = useState('')
  const [olderThan, setOlderThan] = useState<number>(0)
  const [limit, setLimit] = useState<number>(100)
  const [preview, setPreview] = useState<any[] | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [runLoading, setRunLoading] = useState(false)
  const [runResult, setRunResult] = useState<any | null>(null)
  // confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmMessage, setConfirmMessage] = useState('')
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null)

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

  const handlePreview = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    setError(null)
    setPreview(null)
    setRunResult(null)
    setPreviewLoading(true)
    try {
      const res = await adminUploadsCleanupGet({ dir: uploadsDir || undefined, pattern: uploadsPattern, older_than: olderThan || 0, limit })
      setPreview(res.candidates || [])
    } catch (err: any) {
      const msg = err?.message || String(err || 'preview failed')
      setError(msg)
      try { window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message: msg } })) } catch {}
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleRun = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    setError(null)
    // open confirmation modal instead of native confirm
    setConfirmMessage('Are you sure you want to delete matching upload files? This cannot be undone.')
    setConfirmAction(() => async () => {
      setConfirmOpen(false)
      setRunLoading(true)
      setRunResult(null)
      try {
        const res = await adminUploadsCleanupPost({ dir: uploadsDir || undefined, pattern: uploadsPattern, older_than: olderThan || 0, limit })
        setRunResult(res)
        // clear preview after a successful run so UI reflects current state
        setPreview(null)
        try { window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'success', message: `Deleted ${res.count || 0} files` } })) } catch {}
      } catch (err: any) {
        const msg = err?.message || String(err || 'cleanup failed')
        setError(msg)
        try { window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message: msg } })) } catch {}
      } finally {
        setRunLoading(false)
      }
    })
    setConfirmOpen(true)
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Admin Tools</h2>
        <p className="text-sm text-[var(--muted)]">Manage buckets, service tokens, and admin helpers.</p>
      </div>

      {/* Uploads cleanup admin UI */}
      <div className="mb-4 rounded border p-3">
        <h3 className="font-medium">Uploads cleanup</h3>
        <p className="text-xs text-[var(--muted)]">Preview and delete files from the shared uploads directory. Admin only.</p>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-4">
          <input className="rounded border px-2 py-1" placeholder="dir (optional)" value={uploadsDir} onChange={(e) => setUploadsDir(e.target.value)} />
          <input className="rounded border px-2 py-1" placeholder="pattern prefix" value={uploadsPattern} onChange={(e) => setUploadsPattern(e.target.value)} />
          <input className="rounded border px-2 py-1" placeholder="older_than (seconds)" value={String(olderThan)} onChange={(e) => setOlderThan(Number(e.target.value || 0))} />
          <input className="rounded border px-2 py-1" placeholder="limit" value={String(limit)} onChange={(e) => setLimit(Number(e.target.value || 100))} />
        </div>
        <div className="mt-3 flex gap-2">
          <button className="rounded border px-3 py-1" onClick={handlePreview} disabled={previewLoading}>{previewLoading ? 'Preview…' : 'Preview'}</button>
          <button className="rounded bg-[var(--accent)] px-3 py-1 text-white" onClick={handleRun} disabled={runLoading}>{runLoading ? 'Running…' : 'Run clean'}</button>
        </div>

        {preview && (
          <div className="mt-3">
            <div className="text-xs text-[var(--muted)]">Candidates ({preview.length})</div>
            <ul className="mt-2 max-h-40 overflow-auto text-sm list-disc list-inside">
              {preview.map((c: any, i: number) => (
                <li key={i}>{c.path || c.name}</li>
              ))}
            </ul>
          </div>
        )}

        {runResult && (
          <div className="mt-3 text-sm">
            <div className="text-xs text-[var(--muted)]">Deleted: {runResult.count || 0}</div>
            {runResult.errors && runResult.errors.length > 0 && (
              <div className="mt-2 text-xs text-red-600">Errors: {runResult.errors.map((e: any) => e.path + ': ' + e.error).join('; ')}</div>
            )}
          </div>
        )}
      </div>

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
      <ConfirmModal
        open={confirmOpen}
        title="Confirm"
        message={confirmMessage}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => { if (confirmAction) confirmAction() }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}

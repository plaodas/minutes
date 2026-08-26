const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function uploadAudio(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error('upload failed')
  return res.json()
}

export async function getResult(id: string) {
  const res = await fetch(`${BASE}/results/${id}`)
  if (!res.ok) throw new Error('fetch failed')
  return res.json()
}

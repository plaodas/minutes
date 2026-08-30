import fetchWithRetry from '../lib/fetchWithRetry'

const BASE = import.meta.env.VITE_API_BASE || '/api'

export async function uploadAudioBg(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}/transcribe-upload-bg`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error('upload failed')
  return res.json() // { task_id }
}

export function uploadAudioBgWithProgress(file: File, onProgress?: (percent: number) => void) {
  const xhr = new XMLHttpRequest()
  const fd = new FormData()
  fd.append('file', file)
  xhr.open('POST', `${BASE}/transcribe-upload-bg`)

  const promise = new Promise<any>((resolve, reject) => {
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const json = JSON.parse(xhr.responseText)
          resolve(json)
        } catch (e) {
          resolve({})
        }
      } else {
        const msg = `upload failed: ${xhr.status} ${xhr.statusText} ${xhr.responseText || ''}`
        reject(new Error(msg))
      }
    }

    xhr.onerror = () => reject(new Error('upload failed: network error or CORS blocked'))
  })

  if (xhr.upload && onProgress) {
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100)
        onProgress(percent)
      }
    }
  }

  // start send after handlers attached
  xhr.send(fd)

  return { xhr, promise }
}

export async function getBgStatus(taskId: string) {
  const res = await fetchWithRetry(`${BASE}/bg/status/${taskId}`, { credentials: 'same-origin' }, { retries: 3, timeoutMs: 10000 })
  if (!res.ok) throw new Error('status fetch failed')
  return res.json()
}

export async function getBgResult(taskId: string) {
  const res = await fetchWithRetry(`${BASE}/bg/result/${taskId}`, { credentials: 'same-origin' }, { retries: 3, timeoutMs: 10000 })
  if (!res.ok) throw new Error('result fetch failed')
  return res.json()
}

async function _downloadBlob(url: string) {
  const res = await fetchWithRetry(url, { credentials: 'same-origin' }, { retries: 2, timeoutMs: 30000 })
  if (!res.ok) throw new Error(`download failed: ${res.status}`)
  const blob = await res.blob()
  return { blob, headers: res.headers }
}

export async function fetchTranscriptDownload(taskId: string, format: string = 'txt') {
  const url = `${BASE}/bg/transcript/${taskId}?format=${encodeURIComponent(format)}`
  return _downloadBlob(url)
}

export async function fetchSummaryDownload(taskId: string, format: string = 'txt') {
  const url = `${BASE}/bg/summary/${taskId}?format=${encodeURIComponent(format)}`
  return _downloadBlob(url)
}

export async function fetchActionItemsDownload(taskId: string, format: string = 'json') {
  const url = `${BASE}/bg/action-items/${taskId}?format=${encodeURIComponent(format)}`
  return _downloadBlob(url)
}

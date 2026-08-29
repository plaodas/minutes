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
  const res = await fetch(`${BASE}/bg/status/${taskId}`)
  if (!res.ok) throw new Error('status fetch failed')
  return res.json()
}

export async function getBgResult(taskId: string) {
  const res = await fetch(`${BASE}/bg/result/${taskId}`)
  if (!res.ok) throw new Error('result fetch failed')
  return res.json()
}

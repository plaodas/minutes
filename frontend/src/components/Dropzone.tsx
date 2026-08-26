import React, { useCallback, useState } from 'react'
import { motion } from 'framer-motion'
import { uploadAudioBg, uploadAudioBgWithProgress, getBgStatus, getBgResult } from '../api/client'
import { useRef } from 'react'

type Props = {
  setActiveIndex: (i: number) => void
  setResult: (r: any | null) => void
}

function mapStatusToIndex(status: string | undefined) {
  if (!status) return 0
  const s = status.toLowerCase()
  if (s.includes('upload') || s.includes('queued')) return 0
  if (s.includes('preprocess') || s.includes('pre-processing') || s.includes('pre')) return 1
  if (s.includes('transcrib') || s.includes('recognize')) return 2
  if (s.includes('format') || s.includes('formatting')) return 3
  if (s.includes('done') || s.includes('finished') || s.includes('completed') || s.includes('success')) return 4
  return 0
}

export default function Dropzone({ setActiveIndex, setResult }: Props) {
  const [dragActive, setDragActive] = useState(false)
  const [fileName, setFileName] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const xhrRef = useRef<XMLHttpRequest | null>(null)
  const pollRef = useRef<number | null>(null)
  const [running, setRunning] = useState(false)

  const onDrop = useCallback(async (files: FileList | null) => {
    setError(null)
    if (!files || files.length === 0) return
    const f = files[0]
    setFileName(f.name)
    try {
      setActiveIndex(0)
      setUploadProgress(0)
      const resp = await uploadAudioBgWithProgress(f, (p) => setUploadProgress(p))
      const id = resp.task_id || resp.taskId || resp.id
      if (!id) throw new Error('no task id returned')
      setTaskId(id)

      // clear upload progress after upload completes
      setUploadProgress(null)

      // start polling
      const poll = async () => {
        try {
          const st = await getBgStatus(id)
          const status = (st && st.status) || ''
          const backendError = st && (st.error || st.detail || st.message)
          // stop polling if backend reports failed
          if (status.toLowerCase().includes('fail') || backendError) {
            const msg = (backendError && String(backendError)) || 'Task failed'
            setError(msg)
            setActiveIndex(-1)
            // show global toast
            setRunning(true)
            window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message: msg } }))
            return
          }
          const idx = mapStatusToIndex(status)
          setActiveIndex(idx)
          if (status && idx >= 4) {
            // finished
            const res = await getBgResult(id)
            setResult(res)
            setActiveIndex(4)
            return
          }
                  setRunning(false)
                  return
          console.warn('poll error', e)
          setError(String(e?.message || e))
        }
        setTimeout(poll, 2000)
      }
      setTimeout(poll, 1500)
    } catch (e: any) {
      console.error(e)
                  setRunning(false)
                  return
      setActiveIndex(-1)
      setUploadProgress(null)
    }
  }, [setActiveIndex, setResult])

              pollRef.current = window.setTimeout(poll, 2000)
    e.preventDefault()
            pollRef.current = window.setTimeout(poll, 1500)
    onDrop(e.dataTransfer.files)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    onDrop(e.target.files)
  }

  return (
        const cancelAll = useCallback(() => {
          // abort upload
          if (xhrRef.current) {
            try { xhrRef.current.abort() } catch {}
            xhrRef.current = null
          }
          // clear polling
          if (pollRef.current) {
            clearTimeout(pollRef.current)
            pollRef.current = null
          }
          setRunning(false)
          setUploadProgress(null)
          setActiveIndex(-1)
          window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'info', message: 'Upload cancelled' } }))
        }, [setActiveIndex])
    <div>
      <label className={`block p-8 rounded-lg glass-card border border-transparent ${dragActive ? 'drag-active' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <input type="file" accept="audio/*" className="hidden" onChange={handleFileInput} />
        <div className="flex flex-col items-center justify-center gap-4">
          <motion.div animate={{ scale: dragActive ? 1.03 : 1 }} transition={{ type: 'spring', stiffness: 200 }}>
            <div className="text-lg font-medium">Drop your audio file</div>
          </motion.div>
          <div className="text-sm text-[var(--muted)]">MP3 / WAV supported · max 200MB</div>
          {dragActive && (
            <div className="w-full h-8 mt-4 bg-gradient-to-r from-accent/30 to-transparent rounded-md" />
          )}
          {fileName && <div className="mt-2 text-sm text-[var(--muted)]">Selected: {fileName}</div>}
          {uploadProgress !== null && (
            <div className="w-full mt-3">
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-[var(--accent)] h-2 rounded-full" style={{ width: `${uploadProgress}%` }} />
              </div>
              <div className="text-xs text-[var(--muted)] mt-1">Uploading: {uploadProgress}%</div>
            </div>
          )}
          {running && (
            <div className="mt-3">
              <button className="px-3 py-1 rounded bg-gray-200" onClick={cancelAll}>Cancel</button>
            </div>
          )}
          {taskId && <div className="mt-2 text-sm">Task: {taskId}</div>}
          {error && <div className="mt-2 text-sm text-red-600">Error: {error}</div>}
        </div>
      </label>
    </div>
  )
}

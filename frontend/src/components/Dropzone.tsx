import React, { useCallback, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import ErrorModal from './ErrorModal'
import sanitizeError from '../lib/sanitizeError'
import { uploadAudioBgWithProgress, getBgStatus, getBgResult } from '../api/client'

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
  const [lastFile, setLastFile] = useState<File | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastErrorDetails, setLastErrorDetails] = useState<string | null>(null)
  const [showErrorModal, setShowErrorModal] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const xhrRef = useRef<XMLHttpRequest | null>(null)
  const pollRef = useRef<number | null>(0)
  const [running, setRunning] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const onDrop = useCallback(async (files: FileList | null) => {
    setError(null)
    if (!files || files.length === 0) return
    const f = files[0]
    setLastFile(f)
    setFileName(f.name)

    // abort any previous operations
    if (xhrRef.current) {
      try { xhrRef.current.abort() } catch {}
      xhrRef.current = null
    }
    if (pollRef.current) {
      clearTimeout(pollRef.current)
      pollRef.current = 0
    }

    try {
      setActiveIndex(0)
      setUploadProgress(0)
      const { xhr, promise } = uploadAudioBgWithProgress(f, (p) => setUploadProgress(p))
      xhrRef.current = xhr
      const resp = await promise
      const id = resp.task_id || resp.taskId || resp.id
      if (!id) throw new Error('no task id returned')
      setTaskId(id)

      // clear upload UI
      setUploadProgress(null)
      setRunning(true)

      // polling function
      const poll = async () => {
        try {
          const st = await getBgStatus(id)
          const status = (st && st.status) || ''
          const backendError = st && (st.error || st.detail || st.message)

          if (backendError || status.toLowerCase().includes('fail')) {
            const msg = (backendError && String(backendError)) || 'Task failed'
            setError(msg)
            try {
              setLastErrorDetails(sanitizeError(backendError))
            } catch {
              setLastErrorDetails(String(backendError))
            }
            setActiveIndex(-1)
            window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message: msg } }))
            setRunning(false)
            return
          }

          const idx = mapStatusToIndex(status)
          setActiveIndex(idx)
          if (status && idx >= 4) {
            const res = await getBgResult(id)
            setResult(res)
            setActiveIndex(4)
            setRunning(false)
            return
          }
          } catch (err: any) {
          console.warn('poll error', err)
          const detail = err && (err.message || err.toString ? (err.message || err.toString()) : String(err))
          setError(String(detail))
          try { setLastErrorDetails(sanitizeError(err)) } catch { setLastErrorDetails(String(err)) }
          setRunning(false)
          return
        }
        // schedule next poll
        pollRef.current = window.setTimeout(poll, 2000)
      }

      // start first poll shortly after upload completes
      pollRef.current = window.setTimeout(poll, 1500)
    } catch (e: any) {
      console.error(e)
      const msg = String(e?.message || e)
      setError(msg)
      try { setLastErrorDetails(sanitizeError(e)) } catch { setLastErrorDetails(msg) }
      setActiveIndex(-1)
      setUploadProgress(null)
      setRunning(false)
    }
  }, [setActiveIndex, setResult])

  const handleDrop: React.DragEventHandler = (e) => {
    e.preventDefault()
    setDragActive(false)
    onDrop(e.dataTransfer.files)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    onDrop(e.target.files)
  }

  const handleKeyDownOnLabel = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      inputRef.current?.click()
    }
  }

  const handleRetry = () => {
    if (!lastFile) return
    const dt = new DataTransfer()
    dt.items.add(lastFile)
    onDrop(dt.files)
  }

  const cancelAll = useCallback(() => {
    if (xhrRef.current) {
      try { xhrRef.current.abort() } catch {}
      xhrRef.current = null
    }
    if (pollRef.current) {
      clearTimeout(pollRef.current)
      pollRef.current = 0
    }
    setRunning(false)
    setUploadProgress(null)
    setTaskId(null)
    setActiveIndex(-1)
    window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'info', message: 'Upload cancelled' } }))
  }, [setActiveIndex])

  return (
    <div>
      <label
        role="button"
        tabIndex={0}
        aria-label="Upload audio file"
        onKeyDown={handleKeyDownOnLabel}
        className={`block rounded-lg border border-transparent p-5 sm:p-8 glass-card cursor-pointer transition-shadow ${dragActive ? 'drag-active shadow-lg' : 'hover:shadow-md focus:shadow-md'}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <input ref={inputRef} type="file" accept="audio/*" className="hidden" onChange={handleFileInput} />
        <div className="flex flex-col items-center justify-center gap-4">
          <motion.div animate={{ scale: dragActive ? 1.03 : 1 }} transition={{ type: 'spring', stiffness: 200 }}>
            <div className="text-lg font-medium">Drop your audio file</div>
          </motion.div>
          <div className="text-sm text-[var(--muted)]">MP3 / WAV supported · max 200MB</div>
          <div className="mt-2 text-xs text-[var(--accent)]">Tap to select or drop a file</div>
          {dragActive && (
            <div className="w-full h-8 mt-4 bg-gradient-to-r from-accent/30 to-transparent rounded-md" />
          )}
          {fileName && <div className="mt-2 max-w-full break-all text-sm text-[var(--muted)]">Selected: {fileName}</div>}
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
          {taskId && <div className="mt-2 max-w-full break-all text-sm">Task: {taskId}</div>}
          {error && (
            <div className="mt-2 flex items-center gap-3">
              <div className="text-sm text-red-600">Error: {error}</div>
              {lastFile && (
                <button onClick={handleRetry} className="ml-2 rounded bg-[var(--accent)] px-3 py-1 text-xs text-white">Retry</button>
              )}
              <button
                onClick={() => setShowErrorModal(true)}
                className="ml-2 rounded border border-slate-200 bg-white px-3 py-1 text-xs"
              >
                Details
              </button>
            </div>
          )}
          <ErrorModal open={showErrorModal} onClose={() => setShowErrorModal(false)} title="Server response" content={lastErrorDetails} />
        </div>
      </label>
    </div>
  )
}

import React, { useCallback, useState } from 'react'
import { motion } from 'framer-motion'

export default function Dropzone() {
  const [dragActive, setDragActive] = useState(false)
  const [fileName, setFileName] = useState<string | null>(null)

  const onDrop = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return
    const f = files[0]
    setFileName(f.name)
    // TODO: call API upload
  }, [])

  const handleDrop: React.DragEventHandler = (e) => {
    e.preventDefault()
    setDragActive(false)
    onDrop(e.dataTransfer.files)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    onDrop(e.target.files)
  }

  return (
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
        </div>
      </label>
    </div>
  )
}

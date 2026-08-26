import React, { useEffect, useState } from 'react'

type Toast = { id: string; type: 'info' | 'success' | 'error'; message: string }

export default function Toasts() {
  const [toasts, setToasts] = useState<Toast[]>([])

  useEffect(() => {
    const handler = (e: any) => {
      const t: Toast = { id: String(Date.now()) + Math.random().toString(36).slice(2, 8), ...(e.detail || {}) }
      setToasts((s) => [...s, t])
      // auto remove after 6s
      setTimeout(() => {
        setToasts((s) => s.filter((x) => x.id !== t.id))
      }, 6000)
    }

    window.addEventListener('appToast', handler as EventListener)
    return () => window.removeEventListener('appToast', handler as EventListener)
  }, [])

  return (
    <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-50">
      {toasts.map((t) => (
        <div key={t.id} className={`p-3 rounded shadow-lg max-w-xs ${t.type === 'error' ? 'bg-red-50 border border-red-200' : 'bg-white'}`}>
          <div className={`text-sm ${t.type === 'error' ? 'text-red-700' : 'text-gray-900'}`}>{t.message}</div>
        </div>
      ))}
    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { Button } from 'react'
import { applyServiceWorkerUpdate } from '../serviceWorkerRegistration'

export default function UpdateToast() {
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null)

  useEffect(() => {
    const handler = (e: any) => setRegistration(e.detail as ServiceWorkerRegistration)
    window.addEventListener('swUpdated', handler)
    return () => window.removeEventListener('swUpdated', handler)
  }, [])

  if (!registration) return null

  return (
    <div className="fixed bottom-6 right-6 bg-white p-3 rounded-md shadow-lg flex items-center gap-3">
      <div className="text-sm">New version available.</div>
      <div className="flex gap-2">
        <button
          className="px-3 py-1 rounded bg-[var(--accent)] text-white"
          onClick={() => {
            applyServiceWorkerUpdate(registration)
            // reload when controller changes
            navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload())
          }}
        >
          Update
        </button>
      </div>
    </div>
  )
}

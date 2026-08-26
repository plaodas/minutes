import { useCallback, useState } from 'react'
import { requestPushPermission } from '../serviceWorkerRegistration'

export default function usePush() {
  const [enabled, setEnabled] = useState(false)

  const enable = useCallback(async () => {
    const p = await requestPushPermission()
    setEnabled(p === 'granted')
    // TODO: subscribe with VAPID to backend
  }, [])

  return { enabled, enable }
}

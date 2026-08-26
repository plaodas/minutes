// Minimal service worker register + push permission stub
export async function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js')
      console.log('SW registered', reg)

      // Listen for updates and notify the app
      if (reg.waiting) {
        window.dispatchEvent(new CustomEvent('swUpdated', { detail: reg }))
      }

      reg.addEventListener('updatefound', () => {
        const newWorker = reg.installing
        if (!newWorker) return
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && reg.waiting) {
            window.dispatchEvent(new CustomEvent('swUpdated', { detail: reg }))
          }
        })
      })
    } catch (e) {
      console.warn('SW register failed', e)
    }
  }
}

export function applyServiceWorkerUpdate(registration: ServiceWorkerRegistration) {
  if (!registration || !registration.waiting) return
  registration.waiting.postMessage({ type: 'SKIP_WAITING' })
}

export async function requestPushPermission() {
  if (!('Notification' in window)) return null
  const permission = await Notification.requestPermission()
  return permission
}

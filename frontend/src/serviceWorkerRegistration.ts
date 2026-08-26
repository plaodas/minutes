// Minimal service worker register + push permission stub
export async function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js')
      console.log('SW registered', reg)
    } catch (e) {
      console.warn('SW register failed', e)
    }
  }
}

export async function requestPushPermission() {
  if (!('Notification' in window)) return null
  const permission = await Notification.requestPermission()
  return permission
}

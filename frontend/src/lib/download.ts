import { type } from 'os'

export type Runner = () => Promise<{ blob: Blob; headers?: any }>

export async function startDownload(runner: Runner, filename: string, addToast: (msg: string, opts?: any) => string, successMsg = 'Download started') {
  try {
    const { blob } = await runner()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    addToast(successMsg, { level: 'info', duration: 3000 })
  } catch (e: any) {
    addToast('Download failed: ' + (e?.message || e), {
      level: 'error',
      actionLabel: 'Retry',
      action: () => startDownload(runner, filename, addToast, successMsg)
    })
  }
}

export default startDownload

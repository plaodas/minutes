import { describe, it, expect, vi, beforeEach } from 'vitest'
import startDownload from './download'

describe('startDownload', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // mock URL helpers
    // @ts-ignore
    global.URL.createObjectURL = vi.fn(() => 'blob://url')
    // @ts-ignore
    global.URL.revokeObjectURL = vi.fn()
    // ensure anchor click is available
    // @ts-ignore
    HTMLAnchorElement.prototype.click = vi.fn()
  })

  it('calls addToast with success on successful runner', async () => {
    const blob = new Blob(['x'], { type: 'text/plain' })
    const runner = vi.fn().mockResolvedValue({ blob })
    const addToast = vi.fn()
    await startDownload(runner, 'file.txt', addToast, 'OK')
    expect(runner).toHaveBeenCalled()
    expect(addToast).toHaveBeenCalledWith('OK', { level: 'info', duration: 3000 })
    // @ts-ignore
    expect(global.URL.createObjectURL).toHaveBeenCalledWith(blob)
    // @ts-ignore
    expect(global.URL.revokeObjectURL).toHaveBeenCalled()
  })

  it('calls addToast with error and provides retry action that succeeds', async () => {
    const blob = new Blob(['x'])
    let calls = 0
    const runner = vi.fn().mockImplementation(() => {
      calls++
      if (calls === 1) return Promise.reject(new Error('fail1'))
      return Promise.resolve({ blob })
    })
    const addToast = vi.fn()
    await startDownload(runner, 'file.txt', addToast, 'OK')

    // first call should have produced an error toast with an action
    expect(addToast).toHaveBeenCalled()
    const firstCall = addToast.mock.calls[0]
    const opts = firstCall[1]
    expect(firstCall[0]).toContain('Download failed')
    expect(opts).toHaveProperty('actionLabel', 'Retry')
    expect(typeof opts.action).toBe('function')

    // invoke retry action
    await opts.action()

    // now should have called success toast
    const lastCall = addToast.mock.calls[addToast.mock.calls.length - 1]
    expect(lastCall[0]).toBe('OK')
    expect(lastCall[1]).toEqual({ level: 'info', duration: 3000 })
    expect(runner).toHaveBeenCalledTimes(2)
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import fetchWithRetry from './fetchWithRetry'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchWithRetry', () => {
  it('retries on network error and succeeds', async () => {
    const calls: Array<'err'|'ok'> = ['err','err','ok']
    let idx = 0
    globalThis.fetch = vi.fn().mockImplementation(() => {
      const kind = calls[idx++] || 'ok'
      if (kind === 'err') return Promise.reject(new TypeError('network'))
      return Promise.resolve(new Response(JSON.stringify({ok:true}), { status: 200 }))
    }) as any

    const res = await fetchWithRetry('http://example.test/data', {}, { retries: 3, timeoutMs: 1000 })
    expect(res).toBeDefined()
    expect((globalThis.fetch as any).mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('does not retry on 4xx', async () => {
    globalThis.fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('not found', { status: 404 }))) as any
    await expect(fetchWithRetry('http://example.test/404', {}, { retries: 2, timeoutMs: 500 })).rejects.toBeDefined()
    expect((globalThis.fetch as any).mock.calls.length).toEqual(1)
  })

  it('aborts on timeout', async () => {
    globalThis.fetch = vi.fn().mockImplementation((_url: string, init: any) => {
      return new Promise((resolve, reject) => {
        const signal = init && init.signal
        if (signal) {
          signal.addEventListener('abort', () => {
            const err: any = new Error('Aborted')
            err.name = 'AbortError'
            reject(err)
          })
        }
        // never resolve otherwise
      })
    }) as any

    await expect(fetchWithRetry('http://example.test/slow', {}, { retries: 0, timeoutMs: 50 })).rejects.toBeDefined()
  })
})

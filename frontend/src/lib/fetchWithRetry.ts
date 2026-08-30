
export type FetchRetryOptions = {
  retries?: number
  timeoutMs?: number
}

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms))

export async function fetchWithRetry(input: RequestInfo, init?: RequestInit, options?: FetchRetryOptions) {
  const { retries = 3, timeoutMs = 10000 } = options || {}
  let attempt = 0

  while (true) {
    attempt++
    const controller = new AbortController()
    const id = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const res = await fetch(input, { ...init, signal: controller.signal })
      clearTimeout(id)
      // If it's a client error (4xx) that is not authentication, treat as non-retryable
      if (!res.ok && !(res.status >= 500 && res.status < 600)) {
        throw res
      }
      if (!res.ok) throw res
      return res
    } catch (err: any) {
      clearTimeout(id)
      const isAbort = err && err.name === 'AbortError'
      const isTypeError = err instanceof TypeError
      const isNetworkErr = isAbort || isTypeError

      const shouldRetry = isNetworkErr || (err instanceof Response && err.status >= 500 && err.status < 600)

      if (!shouldRetry || attempt > retries) throw err

      const backoff = Math.min(2 ** (attempt - 1) * 1000, 10000)
      // jitter
      const jitter = Math.floor(Math.random() * 200)
      await sleep(backoff + jitter)
      continue
    }
  }
}

export default fetchWithRetry

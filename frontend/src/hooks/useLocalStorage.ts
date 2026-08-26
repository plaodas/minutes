import { useState } from 'react'

export default function useLocalStorage<T>(key: string, initial: T) {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? (JSON.parse(raw) as T) : initial
    } catch {
      return initial
    }
  })

  function setLocal(v: T | ((prev: T) => T)) {
    try {
      const value = typeof v === 'function' ? (v as any)(state) : v
      setState(value)
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // ignore
    }
  }

  return [state, setLocal] as const
}

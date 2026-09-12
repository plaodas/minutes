import { useState } from 'react';

export default function useLocalStorage<T>(key: string, initial: T) {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      // localStorage may be unavailable
      return initial;
    }
  });

  function setLocal(v: T | ((prev: T) => T)) {
    try {
      const value = typeof v === 'function' ? (v as (prev: T) => T)(state) : v;
      setState(value);
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // localStorage may be unavailable or quota-exceeded
    }
  }

  return [state, setLocal] as const;
}

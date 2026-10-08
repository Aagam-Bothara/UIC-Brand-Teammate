import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { loadJSON, saveJSON } from './storage'

/**
 * useState that is restored from and saved to localStorage (SPEC: browser localStorage persistence).
 * `sanitize` validates the restored value (it may be corrupt or from an older app version); returning
 * null/undefined falls back to `initial`. Without it, any non-null JSON value of the wrong type would
 * be trusted and could crash the app on every load.
 */
export function usePersistentState<T>(
  key: string,
  initial: T,
  sanitize?: (raw: unknown) => T | null | undefined,
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    const raw = loadJSON<unknown>(key, undefined)
    if (raw === undefined) return initial
    if (!sanitize) return raw as T
    try {
      return sanitize(raw) ?? initial
    } catch {
      return initial
    }
  })
  useEffect(() => {
    saveJSON(key, value)
  }, [key, value])
  return [value, setValue]
}

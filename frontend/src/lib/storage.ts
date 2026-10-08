/** localStorage helpers that never throw (private mode, quota, disabled storage). */

const PREFIX = 'uic-editorial:'

export function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function saveJSON(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    // Storage unavailable or full: persistence is best-effort. Drop any older value under this key so
    // a reload doesn't restore it next to newer state (e.g. an old analysis beside the new draft).
    removeKey(key)
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(PREFIX + key)
  } catch {
    /* ignore */
  }
}

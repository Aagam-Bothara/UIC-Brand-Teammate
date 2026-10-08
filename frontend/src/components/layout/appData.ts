/** localStorage prefix used by src/lib/storage.ts for everything this app persists. */
export const APP_STORAGE_PREFIX = 'uic-editorial:'

/** Remove every persisted key of this app (draft, results, settings). Never throws. */
export function clearAppData(): void {
  try {
    const keys: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(APP_STORAGE_PREFIX)) keys.push(key)
    }
    keys.forEach((k) => localStorage.removeItem(k))
  } catch {
    /* storage unavailable */
  }
}

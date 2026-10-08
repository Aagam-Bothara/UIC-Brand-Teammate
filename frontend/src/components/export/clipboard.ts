/** Copy text to the clipboard: async Clipboard API first, hidden-textarea + execCommand fallback. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* permission denied / insecure context — fall through to the legacy path */
  }
  if (typeof document === 'undefined' || typeof document.execCommand !== 'function') return false
  const active = document.activeElement as HTMLElement | null
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.setAttribute('aria-hidden', 'true')
  Object.assign(ta.style, { position: 'fixed', top: '0', left: '0', opacity: '0', pointerEvents: 'none' })
  document.body.appendChild(ta)
  try {
    ta.focus()
    ta.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(ta)
    active?.focus?.()
  }
}

/** Trigger a browser download of `blob` as `filename`. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Local-date stamp YYYY-MM-DD (not UTC, so it matches the user's calendar). */
export function dateStamp(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export const reportFilename = (d?: Date) => `uic-editorial-report-${dateStamp(d)}.pdf`
export const textFilename = (d?: Date) => `uic-editorial-text-${dateStamp(d)}.txt`

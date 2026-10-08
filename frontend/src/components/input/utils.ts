/** Small helpers shared by TextInput and RulesetPanel (Workstream 4, Tasks 4.4 / 4.5). */

const nf = new Intl.NumberFormat('en-US')

/** 5000 → "5,000" */
export const fmt = (n: number): string => nf.format(n)

/** Pluralize: plural(1, 'word') → "1 word", plural(3, 'word') → "3 words". */
export const plural = (n: number, noun: string): string => `${fmt(n)} ${noun}${n === 1 ? '' : 's'}`

/** True on macOS / iOS, where the analyze shortcut is ⌘ rather than Ctrl. */
export function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  const p = nav.userAgentData?.platform ?? nav.platform ?? nav.userAgent ?? ''
  return /mac|iphone|ipad|ipod/i.test(p)
}

/** Label for the analyze shortcut modifier key. */
export const modKeyLabel = (): string => (isApplePlatform() ? '⌘' : 'Ctrl')

/** Whether the async Clipboard API can read text in this browser. */
export function canReadClipboard(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.clipboard?.readText === 'function'
}

/** Join class names, skipping falsy values. */
export const cx = (...parts: (string | false | null | undefined)[]): string => parts.filter(Boolean).join(' ')

export type MeterTone = 'ok' | 'near' | 'over'

/** Fraction of the word limit at which the meter turns amber. */
export const NEAR_LIMIT = 0.85

/** Meter color band for the word count: navy → amber near the limit → red over it. */
export function meterTone(words: number, maxWords: number, overLimit: boolean): MeterTone {
  if (overLimit) return 'over'
  return words >= maxWords * NEAR_LIMIT ? 'near' : 'ok'
}

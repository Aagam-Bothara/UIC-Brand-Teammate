import type { ChangeDecision } from '../../lib/changes'
import type { Change, Severity } from '../../types/api'

/** Visual/semantic state of one change in the improved text. */
export type ChangeState = 'applied' | 'hidden' | 'accepted' | 'rejected'

export function changeState(applied: boolean, decision: ChangeDecision | undefined): ChangeState {
  if (decision === 'accepted') return 'accepted'
  if (decision === 'rejected') return 'rejected'
  return applied ? 'applied' : 'hidden'
}

export const STATE_LABEL: Record<ChangeState, string> = {
  applied: 'Applied',
  hidden: 'Not shown',
  accepted: 'Accepted',
  rejected: 'Rejected',
}

/** `${color}` + 2-digit hex alpha, e.g. tint('#3B82F6', '26') → 15% tint (DESIGN.md). */
export const tint = (color: string, alpha: string) => (/^#[0-9a-f]{6}$/i.test(color) ? `${color}${alpha}` : color)

export const SEVERITY_STYLE: Record<Severity, { label: string; color: string }> = {
  high: { label: 'High', color: '#D50032' },
  medium: { label: 'Medium', color: '#B45309' },
  low: { label: 'Low', color: '#4B5563' },
}

/**
 * Collapse whitespace and clip long text for one-line summaries. Whitespace-only text (e.g. a
 * removed double space or an added paragraph break) gets a visible name instead of becoming "".
 */
export function snippet(text: string, max = 60): string {
  const t = text.replace(/\s+/g, ' ').trim()
  if (!t) return text ? (/[\r\n]/.test(text) ? '(line break)' : '(space)') : ''
  const chars = Array.from(t) // don't split emoji / surrogate pairs
  return chars.length > max ? `${chars.slice(0, max - 1).join('').trimEnd()}…` : t
}

/** Short human description of an edit, e.g. “Hey guys” → “Hello, everyone”. */
export function describeChange(c: Change, max = 60): string {
  const before = snippet(c.original_text, max)
  const after = snippet(c.rewritten_text, max)
  if (!before) return `Insert “${after}”`
  if (!after) return `Remove “${before}”`
  return `“${before}” → “${after}”`
}

export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/**
 * The on-screen element for a change. Prefers the improved pane, then the original pane, and a
 * visible element over a hidden one (only one pane is visible on narrow screens).
 */
export function findChangeAnchor(root: ParentNode | null, changeId: string): HTMLElement | null {
  if (!root) return null
  const id = changeId.replace(/["\\]/g, '\\$&')
  const all = ['improved', 'original'].flatMap((pane) =>
    Array.from(root.querySelectorAll<HTMLElement>(`[data-anchor="${pane}"][data-change-id="${id}"]`)),
  )
  return all.find((el) => el.getClientRects().length > 0) ?? all[0] ?? null
}

/** The focusable trigger for a change (the highlighted mark, else its row in the changes list). */
export function findChangeTrigger(root: ParentNode | null, changeId: string): HTMLElement | null {
  if (!root) return null
  const id = changeId.replace(/["\\]/g, '\\$&')
  const all = ['mark', 'list'].flatMap((kind) =>
    Array.from(root.querySelectorAll<HTMLElement>(`[data-change-trigger="${kind}"][data-change-id="${id}"]`)),
  )
  return all.find((el) => el.getClientRects().length > 0) ?? all[0] ?? null
}

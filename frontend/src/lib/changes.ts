import type { Change, RulesetId } from '../types/api'

/** Per-change user decision (FR-10 hybrid acceptance). Absent = follow the ruleset toggle. */
export type ChangeDecision = 'accepted' | 'rejected'
export type Decisions = Record<string, ChangeDecision>

/** Whether a change is currently applied, given revealed rulesets and individual decisions. */
export function isChangeApplied(change: Change, revealed: ReadonlySet<RulesetId>, decisions: Decisions): boolean {
  const d = decisions[change.change_id]
  if (d === 'accepted') return true
  if (d === 'rejected') return false
  return revealed.has(change.ruleset)
}

export type Segment =
  | { kind: 'equal'; text: string }
  | { kind: 'change'; change: Change; applied: boolean; text: string }

/**
 * Sort changes by position and drop any that overlap an earlier one or fall outside the text.
 * The backend guarantees non-overlapping changes; this keeps the UI safe if it doesn't.
 */
export function normalizeChanges(original: string, changes: Change[]): Change[] {
  const sorted = [...changes].sort(
    (a, b) => a.original_start - b.original_start || a.original_end - b.original_end,
  )
  const out: Change[] = []
  let cursor = 0
  for (const c of sorted) {
    const { original_start: start, original_end: end } = c
    // Non-integer / missing offsets (bad backend data) would silently corrupt the text: drop them.
    if (!Number.isInteger(start) || !Number.isInteger(end)) continue
    if (start < cursor || end < start || end > original.length) continue
    out.push(c)
    cursor = c.original_end
  }
  return out
}

/**
 * Split the original text into equal / change segments. For a change segment, `text` is the
 * rewritten text when applied, else the original span.
 */
export function buildSegments(original: string, changes: Change[], isApplied: (c: Change) => boolean): Segment[] {
  const segments: Segment[] = []
  let cursor = 0
  for (const c of normalizeChanges(original, changes)) {
    if (c.original_start > cursor) segments.push({ kind: 'equal', text: original.slice(cursor, c.original_start) })
    const applied = isApplied(c)
    segments.push({
      kind: 'change',
      change: c,
      applied,
      text: applied ? c.rewritten_text : original.slice(c.original_start, c.original_end),
    })
    cursor = c.original_end
  }
  if (cursor < original.length) segments.push({ kind: 'equal', text: original.slice(cursor) })
  return segments
}

/** The text that results from applying the selected changes to the original. */
export function applyChanges(original: string, changes: Change[], isApplied: (c: Change) => boolean): string {
  return buildSegments(original, changes, isApplied)
    .map((s) => s.text)
    .join('')
}

export function countWords(text: string): number {
  const t = text.trim()
  return t ? t.split(/\s+/).length : 0
}

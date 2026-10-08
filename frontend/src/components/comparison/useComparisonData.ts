import { useMemo } from 'react'
import { RULESET_ORDER } from '../../config/rulesets'
import { buildSegments, isChangeApplied, normalizeChanges, type Decisions, type Segment } from '../../lib/changes'
import type { AnalyzeResponse, Change, Issue, RulesetId } from '../../types/api'

export interface RulesetSummary {
  id: RulesetId
  /** Number of changes this ruleset contributed. */
  total: number
  /** How many of them are currently applied (after decisions). */
  applied: number
}

export interface ComparisonData {
  /** Non-overlapping changes in document order. */
  changes: Change[]
  changeIndex: Map<string, number>
  segments: Segment[]
  appliedIds: ReadonlySet<string>
  appliedCount: number
  /** Rulesets present in the analysis, SPEC order. */
  rulesets: RulesetSummary[]
  /** Rulesets that have at least one change — the ones that can be revealed. */
  available: RulesetId[]
  issuesById: Map<string, Issue>
  /** Decisions that refer to changes in this analysis. */
  decisionCount: number
}

/**
 * Everything ComparisonView derives from the analysis. Structural data (normalised changes, issue
 * lookup) only recomputes when the analysis changes; segments recompute on reveal/decision changes.
 * Both are linear in text size, so 5,000-word drafts stay instant.
 */
export function useComparisonData(
  analysis: AnalyzeResponse | null,
  revealed: ReadonlySet<RulesetId>,
  decisions: Decisions,
): ComparisonData | null {
  const structure = useMemo(() => {
    if (!analysis) return null
    const changes = normalizeChanges(analysis.original, analysis.changes)
    const changeIndex = new Map(changes.map((c, i) => [c.change_id, i]))
    const issuesById = new Map(analysis.issues.map((i) => [i.issue_id, i]))
    const present = RULESET_ORDER.filter(
      (r) => analysis.rulesets.includes(r) || changes.some((c) => c.ruleset === r),
    )
    return { changes, changeIndex, issuesById, present }
  }, [analysis])

  return useMemo(() => {
    if (!analysis || !structure) return null
    const { changes, changeIndex, issuesById, present } = structure
    const isApplied = (c: Change) => isChangeApplied(c, revealed, decisions)
    const segments = buildSegments(analysis.original, changes, isApplied)
    const appliedIds = new Set<string>()
    for (const s of segments) if (s.kind === 'change' && s.applied) appliedIds.add(s.change.change_id)
    const rulesets: RulesetSummary[] = present.map((id) => {
      const mine = changes.filter((c) => c.ruleset === id)
      return { id, total: mine.length, applied: mine.filter((c) => appliedIds.has(c.change_id)).length }
    })
    return {
      changes,
      changeIndex,
      segments,
      appliedIds,
      appliedCount: appliedIds.size,
      rulesets,
      available: rulesets.filter((r) => r.total > 0).map((r) => r.id),
      issuesById,
      decisionCount: changes.filter((c) => decisions[c.change_id]).length,
    }
  }, [analysis, structure, revealed, decisions])
}

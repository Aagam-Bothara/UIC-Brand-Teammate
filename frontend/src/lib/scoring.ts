import type { ComplianceStatus, Issue, RulesetId, Severity } from '../types/api'

/**
 * Mirrors Workstream 2's backend/services/scoring_service.py so the live "now" scores the UI
 * recomputes (as changes are toggled) match what the backend reports.
 */

/** SPEC 1: start at 100, deduct by severity, floor at 0. */
export const SEVERITY_DEDUCTION: Record<Severity, number> = { high: 10, medium: 5, low: 2 }

/** WS2: a single rule deducts for at most 3 occurrences (every occurrence still counts as an issue). */
export const MAX_DEDUCTIONS_PER_RULE = 3

/** WS2 score groups: which rulesets feed the brand and accessibility scores. */
export const SCORE_GROUPS: Record<'brand' | 'accessibility', RulesetId[]> = {
  brand: ['brand', 'content', 'audience_tone'],
  accessibility: ['accessibility', 'reading_level'],
}

export function scoreFor(issues: Issue[]): number {
  const perRule: Record<string, number> = {}
  let deduction = 0
  for (const i of issues) {
    const n = perRule[i.rule_id] ?? 0
    if (n >= MAX_DEDUCTIONS_PER_RULE) continue
    perRule[i.rule_id] = n + 1
    deduction += SEVERITY_DEDUCTION[i.severity]
  }
  return Math.max(0, 100 - deduction)
}

/**
 * SPEC 1 / WS2 status classification (checked in this order, on the lower of the two scores):
 *  - Major Revisions: a score < 70 OR more than 5 issues
 *  - Approved: both scores ≥ 90 AND at most 2 issues
 *  - Minor Revisions: everything else
 */
export function classify(brand: number, accessibility: number, totalIssues: number): ComplianceStatus {
  const low = Math.min(brand, accessibility)
  if (low < 70 || totalIssues > 5) return 'Major Revisions Needed'
  if (low >= 90 && totalIssues <= 2) return 'Approved'
  return 'Minor Revisions Needed'
}

/** Brand/accessibility scores and status for a set of still-open issues. */
export function computeScores(openIssues: Issue[]): { brand: number; accessibility: number; total_issues: number; status: ComplianceStatus } {
  const inGroup = (g: keyof typeof SCORE_GROUPS) => openIssues.filter((i) => SCORE_GROUPS[g].includes(i.ruleset))
  const brand = scoreFor(inGroup('brand'))
  const accessibility = scoreFor(inGroup('accessibility'))
  return { brand, accessibility, total_issues: openIssues.length, status: classify(brand, accessibility, openIssues.length) }
}

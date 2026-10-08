/**
 * Parity: the frontend's live "now" scores (lib/scoring.ts) must equal Workstream 2's backend
 * scoring_service.calculate_scores on the same issues. Fixture = the backend rule engine run on the
 * 24 synthetic demo drafts (data/demo/demo_drafts.json); regenerate it if the backend scoring changes.
 */
import { describe, expect, it } from 'vitest'
import { statusFromApi } from '../../services/ws2Adapter'
import type { Issue } from '../../types/api'
import { computeScores } from '../scoring'
import fixture from './fixtures/ws2_scores.json'

type Row = { id: string; issues: Pick<Issue, 'issue_id' | 'rule_id' | 'ruleset' | 'severity'>[]; expected: { brand: number; accessibility: number; total_issues: number; status: string } }

describe('scoring parity with the backend (WS2)', () => {
  it.each((fixture as Row[]).map((r) => [r.id, r] as const))('%s', (_id, row) => {
    const issues = row.issues.map((i) => ({ ...i, message: '', start: 0, end: 0, excerpt: '' })) as Issue[]
    expect(computeScores(issues)).toEqual({
      brand: row.expected.brand,
      accessibility: row.expected.accessibility,
      total_issues: row.expected.total_issues,
      status: statusFromApi(row.expected.status),
    })
  })

  it('covers all three statuses', () => {
    expect(new Set((fixture as Row[]).map((r) => r.expected.status))).toEqual(new Set(['Approved', 'Minor Revisions', 'Major Revisions']))
  })
})

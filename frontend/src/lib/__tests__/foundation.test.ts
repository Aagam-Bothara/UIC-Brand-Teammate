import { describe, expect, it } from 'vitest'
import { RULESET_ORDER } from '../../config/rulesets'
import { SAMPLE_TEXT, mockAnalyze, runMockRules } from '../../services/mockData'
import type { Change } from '../../types/api'
import { applyChanges, buildSegments, countWords, isChangeApplied, normalizeChanges } from '../changes'
import { fleschKincaidGrade } from '../readability'
import { classify, computeScores, scoreFor } from '../scoring'

const chg = (id: string, s: number, e: number, rewritten: string, ruleset: Change['ruleset'] = 'brand'): Change => ({
  change_id: id, ruleset, original_start: s, original_end: e, original_text: '', rewritten_text: rewritten,
  explanation: '', issue_ids: [],
})

describe('changes', () => {
  const original = 'Hello big world'
  const changes = [chg('b', 10, 15, 'planet', 'content'), chg('a', 0, 5, 'Hi')]

  it('applies selected changes by offset regardless of input order', () => {
    expect(applyChanges(original, changes, () => true)).toBe('Hi big planet')
    expect(applyChanges(original, changes, (c) => c.change_id === 'b')).toBe('Hello big planet')
    expect(applyChanges(original, changes, () => false)).toBe(original)
  })

  it('builds segments covering the whole text', () => {
    const segs = buildSegments(original, changes, (c) => c.change_id === 'a')
    expect(segs.map((s) => s.kind)).toEqual(['change', 'equal', 'change'])
    expect(segs.map((s) => s.text).join('')).toBe('Hi big world')
  })

  it('drops overlapping and out-of-range changes', () => {
    const bad = [chg('a', 0, 5, 'X'), chg('b', 3, 8, 'Y'), chg('c', 10, 99, 'Z'), chg('d', 7, 6, 'W')]
    expect(normalizeChanges(original, bad).map((c) => c.change_id)).toEqual(['a'])
  })

  it('supports insertions and deletions', () => {
    expect(applyChanges('ab', [chg('i', 1, 1, '-'), chg('d', 1, 2, '')], () => true)).toBe('a-')
  })

  it('decisions override ruleset reveal', () => {
    const c = chg('x', 0, 1, 'y', 'brand')
    expect(isChangeApplied(c, new Set(['brand']), {})).toBe(true)
    expect(isChangeApplied(c, new Set(['brand']), { x: 'rejected' })).toBe(false)
    expect(isChangeApplied(c, new Set(), { x: 'accepted' })).toBe(true)
    expect(isChangeApplied(c, new Set(), {})).toBe(false)
  })

  it('counts words', () => {
    expect(countWords('  one two\nthree ')).toBe(3)
    expect(countWords('   ')).toBe(0)
  })
})

describe('scoring (SPEC 1)', () => {
  const issue = (ruleset: 'brand' | 'accessibility' | 'content', severity: 'high' | 'medium' | 'low') => ({
    issue_id: Math.random().toString(), ruleset, rule_id: 'r', severity, message: '', start: 0, end: 0, excerpt: '',
  })
  it('deducts by severity, caps each rule at 3 deductions, floors at 0', () => {
    expect(scoreFor([issue('brand', 'high'), issue('brand', 'medium'), issue('brand', 'low')])).toBe(83)
    expect(scoreFor(Array.from({ length: 12 }, () => issue('brand', 'high')))).toBe(70)
    expect(scoreFor(Array.from({ length: 12 }, (_, n) => ({ ...issue('brand', 'high'), rule_id: `r${n}` })))).toBe(0)
  })
  it('classifies status', () => {
    expect(classify(100, 95, 2)).toBe('Approved')
    expect(classify(100, 95, 3)).toBe('Minor Revisions Needed')
    expect(classify(85, 100, 1)).toBe('Minor Revisions Needed')
    expect(classify(65, 100, 1)).toBe('Major Revisions Needed')
    expect(classify(100, 100, 6)).toBe('Major Revisions Needed')
  })
  it('uses WS2 score groups (brand+content+tone, accessibility+reading level)', () => {
    const s = computeScores([issue('brand', 'high'), issue('accessibility', 'low'), { ...issue('content', 'high'), rule_id: 'c' }])
    expect(s).toMatchObject({ brand: 80, accessibility: 98, total_issues: 3, status: 'Minor Revisions Needed' })
  })
})

describe('mock analyzer', () => {
  it('produces non-overlapping changes whose offsets match the original', () => {
    const { changes, issues } = runMockRules(SAMPLE_TEXT, RULESET_ORDER)
    expect(changes.length).toBeGreaterThanOrEqual(10)
    expect(normalizeChanges(SAMPLE_TEXT, changes)).toHaveLength(changes.length)
    for (const c of changes) expect(SAMPLE_TEXT.slice(c.original_start, c.original_end)).toBe(c.original_text)
    expect(new Set(changes.map((c) => c.ruleset))).toEqual(new Set(RULESET_ORDER))
    expect(issues).toHaveLength(changes.length)
  })

  it('rewrites the sample into UIC style', () => {
    const r = mockAnalyze({ text: SAMPLE_TEXT, audience: 'Students', channel: 'Email', rulesets: RULESET_ORDER })
    expect(r.rewritten).toContain('University of Illinois Chicago')
    expect(r.rewritten).toContain('March 5 from noon to 4 p.m.')
    expect(r.rewritten).toContain('Register online')
    expect(r.rewritten).toContain('Hello, everyone')
    expect(r.rewritten).not.toMatch(/!!|AMAZING|ASAP|utilize/)
    expect(r.scores.status).toBe('Major Revisions Needed')
  })

  it('only runs selected rulesets', () => {
    const r = mockAnalyze({ text: SAMPLE_TEXT, audience: 'Faculty', channel: 'Website', rulesets: ['brand'] })
    expect(r.changes.every((c) => c.ruleset === 'brand')).toBe(true)
    expect(r.scores.reading_level.target).toBe(10)
  })
})

describe('readability', () => {
  it('ranks simple text below complex text', () => {
    expect(fleschKincaidGrade('The cat sat. The dog ran.')).toBeLessThan(
      fleschKincaidGrade('Institutional accountability necessitates comprehensive interdisciplinary collaboration among stakeholders.'),
    )
    expect(fleschKincaidGrade('')).toBe(0)
  })
})

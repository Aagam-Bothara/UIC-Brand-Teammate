import { describe, expect, it } from 'vitest'
import { RULESET_ORDER } from '../../config/rulesets'
import { adaptAudiences, adaptCheck, adaptRules, codePointToUtf16, statusFromApi } from '../ws2Adapter'

describe('ws2Adapter', () => {
  it('maps the wrapped, alphabetical /api/rules response to SPEC order with API colors', () => {
    const r = adaptRules({ rulesets: [
      { ruleset_id: 'content', ruleset_name: 'Content & Style Rules', highlight_color: '#F59E0B', rule_count: 31, enabled: true },
      { ruleset_id: 'brand', ruleset_name: 'Brand Compliance Rules', highlight_color: '#123456', rule_count: 19, enabled: true },
    ] })
    expect(r.map((x) => x.ruleset_id)).toEqual(['brand', 'content'])
    expect(r[0]).toMatchObject({ ruleset_name: 'Brand', highlight_color: '#123456', rule_count: 19 })
    expect(adaptRules({}).map((x) => x.ruleset_id)).toEqual(RULESET_ORDER)
  })

  it('maps audiences', () => {
    const a = adaptAudiences({ audiences: [{ audience_id: 'faculty', label: 'Faculty', target_grade_level: 10 }], channels: [] })
    expect(a).toEqual([expect.objectContaining({ id: 'Faculty', reading_level_target: 10 })])
  })

  it('maps statuses', () => {
    expect(statusFromApi('Minor Revisions')).toBe('Minor Revisions Needed')
    expect(statusFromApi('Approved')).toBe('Approved')
  })

  it('converts code-point offsets to UTF-16 (emoji)', () => {
    const text = '🎉🎉 Hey guys'
    const conv = codePointToUtf16(text)
    expect(text.slice(conv(3), conv(11))).toBe('Hey guys')
  })

  it('adapts a /api/rules/check response', () => {
    const text = '🎉 Hey guys'
    const out = adaptCheck(text, {
      analysis: { audience: 'students', reading_level: { grade_level: 6.6, target_grade: 8 }, issues: [
        { issue_id: 'tone-002-1', rule_id: 'tone-002', ruleset_id: 'audience_tone', severity: 'medium', message: 'm', matched_text: 'Hey guys', start: 2, end: 10, scope: 'span', suggestion: 'Hi everyone' },
      ] },
      scores: { brand_score: 66, accessibility_score: 83, total_issues: 14, status: 'Major Revisions' },
    })
    const i = out.issues[0]
    expect(text.slice(i.start, i.end)).toBe('Hey guys')
    expect(i).toMatchObject({ ruleset: 'audience_tone', excerpt: 'Hey guys', scope: 'span' })
    expect(out.scores).toMatchObject({ brand: 66, accessibility: 83, status: 'Major Revisions Needed', reading_level: { grade: 6.6, target: 8, audience: 'Students' } })
  })
})

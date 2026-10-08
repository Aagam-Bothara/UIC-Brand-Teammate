/**
 * QA regression tests for the shared foundation (lib/*, services/*). Each test reproduces a bug that
 * was found and fixed; keep them so it can't come back.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RULESET_ORDER } from '../../config/rulesets'
import { runMockRules } from '../../services/mockData'
import { adaptAudiences, adaptRules } from '../../services/ws2Adapter'
import type { Change } from '../../types/api'
import { applyChanges, normalizeChanges } from '../changes'
import { countSyllables, fleschKincaidGrade } from '../readability'
import { sanitizeAnalysis, sanitizeChat, sanitizeDecisions, sanitizeRulesetIds } from '../sanitize'
import { loadJSON, saveJSON } from '../storage'

const chg = (id: string, s: number, e: number, rewritten: string): Change => ({
  change_id: id, ruleset: 'brand', original_start: s, original_end: e, original_text: '', rewritten_text: rewritten,
  explanation: '', issue_ids: [],
})

describe('changes edge cases', () => {
  it('drops changes with non-integer / missing offsets instead of corrupting the text', () => {
    const bad = { ...chg('nan', 0, 0, 'X'), original_start: undefined as unknown as number, original_end: undefined as unknown as number }
    const frac = chg('frac', 1.5, 2.5, 'Y')
    const ok = chg('ok', 6, 11, 'there')
    expect(normalizeChanges('Hello world', [bad, frac, ok]).map((c) => c.change_id)).toEqual(['ok'])
    expect(applyChanges('Hello world', [bad, frac, ok], () => true)).toBe('Hello there')
  })

  it('keeps several insertions at the same index and an adjacent replacement, in order', () => {
    const changes = [chg('r', 2, 4, 'CD'), chg('i1', 2, 2, '1'), chg('i2', 2, 2, '2')]
    expect(applyChanges('abcdef', changes, () => true)).toBe('ab12CDef')
  })

  it('handles emoji (surrogate pairs) and CRLF text by UTF-16 offset', () => {
    const t = 'Hi 👋\r\nUIC rocks'
    const start = t.indexOf('UIC')
    expect(applyChanges(t, [chg('a', start, start + 3, 'University of Illinois Chicago')], () => true)).toBe(
      'Hi 👋\r\nUniversity of Illinois Chicago rocks',
    )
    expect(applyChanges('', [chg('ins', 0, 0, 'New')], () => true)).toBe('New')
  })
})

describe('readability parity with backend/services/reading_level.py', () => {
  // Reference values computed by running the Python compute_metrics() on the same strings.
  it.each([
    ['Register for classes\nPay tuition\nBuy your books\nMeet your adviser\nVisit the campus library today', 5.6],
    ['The cat sat. The dog ran.', 0],
    ['Institutional accountability necessitates comprehensive interdisciplinary collaboration among stakeholders.', 42.1],
    ['Join us at 3 p.m. Tuesday in the Student Center East. Dr. Smith will speak, e.g. about beautiful media and actual video.', 5.4],
    ["Hey guys!\n\nThe University of Illinois at Chicago is great. It's well-known and state-of-the-art!! Really?", 3.7],
    ['Quiet people create every idea.', 14.7],
    ['123 456', 0],
    ['', 0],
  ])('grade(%j) = %d', (text, grade) => {
    expect(fleschKincaidGrade(text)).toBeCloseTo(grade, 1)
  })

  it.each([
    ['beautiful', 3], ['media', 3], ['social', 2], ['actual', 3], ['quality', 3], ['video', 3], ['boxes', 2],
    ['wanted', 2], ['loved', 1], ['table', 2], ['agree', 2], ['churches', 2], ['changes', 2], ['university', 5],
  ])('syllables(%s) = %d', (word, n) => {
    expect(countSyllables(word)).toBe(n)
  })
})

describe('storage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('does not leave an older value behind when saving fails (quota exceeded)', () => {
    saveJSON('analysis', { analysis_id: 'old' })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    saveJSON('analysis', { analysis_id: 'new' })
    vi.restoreAllMocks()
    // Restoring the OLD analysis next to the NEW draft/decisions would be wrong: fall back instead.
    expect(loadJSON('analysis', null)).toBeNull()
  })
})

describe('sanitize (persisted / API data of unknown shape)', () => {
  const base = {
    analysis_id: 'a1', original: 'Hello UIC', rewritten: 'Hello UIC', audience: 'Students', channel: 'Email',
    rulesets: ['brand'], model_used: 'mock', latency_ms: 0, guidelines: [],
    changes: [{ change_id: 'c1', ruleset: 'brand', original_start: 6, original_end: 9, original_text: 'UIC', rewritten_text: 'University of Illinois Chicago', explanation: '', issue_ids: ['i1'] }],
    issues: [{ issue_id: 'i1', ruleset: 'brand', rule_id: 'brand-001', severity: 'high', message: 'm', start: 6, end: 9, excerpt: 'UIC' }],
    scores: { brand: 90, accessibility: 100, total_issues: 1, status: 'Approved', reading_level: { grade: 2, target: 8, audience: 'Students' } },
  }

  it('rejects garbage', () => {
    for (const v of [null, 42, 'x', [], {}, { original: 'x' }, { ...base, original: 3 }]) expect(sanitizeAnalysis(v)).toBeNull()
  })

  it('fills fields missing from an older persisted shape', () => {
    const old = { original: base.original, changes: [{ ...base.changes[0], issue_ids: undefined }], issues: base.issues }
    const a = sanitizeAnalysis(old)!
    expect(a).not.toBeNull()
    expect(a.changes[0].issue_ids).toEqual([])
    expect(a.guidelines).toEqual([])
    expect(a.audience).toBe('Students')
    expect(a.channel).toBe('Email')
    expect(a.rulesets).toEqual(['brand'])
    expect(a.rewritten).toBe('Hello University of Illinois Chicago')
    expect(a.scores).toMatchObject({ brand: 90, accessibility: 100, total_issues: 1, status: 'Approved' })
    expect(a.scores.reading_level.target).toBe(8)
  })

  it('normalizes WS2 vocab (status, lowercase audience/channel/severity) and drops invalid items', () => {
    const a = sanitizeAnalysis({
      ...base,
      audience: 'faculty', channel: 'social_media', rulesets: ['content', 'brand', 'bogus'],
      scores: { ...base.scores, status: 'Minor Revisions' },
      issues: [...base.issues, { ...base.issues[0], issue_id: 'i2', severity: 'HIGH' }, { ...base.issues[0], issue_id: 'i3', severity: 'critical' }, null],
      changes: [...base.changes, { change_id: 'c2', ruleset: 'nope', original_start: 0, original_end: 1, rewritten_text: 'x' }, 7],
    })!
    expect(a.audience).toBe('Faculty')
    expect(a.channel).toBe('Social Media')
    expect(a.rulesets).toEqual(['brand', 'content'])
    expect(a.scores.status).toBe('Minor Revisions Needed')
    expect(a.issues.map((i) => [i.issue_id, i.severity])).toEqual([['i1', 'high'], ['i2', 'high']])
    expect(a.changes.map((c) => c.change_id)).toEqual(['c1'])
  })

  it('drops decisions for unknown changes and bad values; drops malformed chat messages', () => {
    const a = sanitizeAnalysis(base)!
    expect(sanitizeDecisions({ c1: 'accepted', ghost: 'rejected', c2: 'maybe' }, a)).toEqual({ c1: 'accepted' })
    expect(sanitizeDecisions({ c1: 'accepted' }, null)).toEqual({})
    expect(sanitizeDecisions('nope', a)).toBeNull()
    const chat = sanitizeChat([{ id: 'm1', role: 'user', content: 'hi', created_at: 'x' }, { role: 'system', content: 'x' }, null, { role: 'assistant', content: 'yo' }])!
    expect(chat.map((m) => m.content)).toEqual(['hi', 'yo'])
    expect(chat[1].id).toBeTruthy()
    expect(sanitizeChat({})).toBeNull()
    expect(sanitizeRulesetIds(['audience_tone', 'brand', 'zzz', 'brand'])).toEqual(['brand', 'audience_tone'])
    expect(sanitizeRulesetIds('brand')).toBeNull()
  })
})

describe('mock rules', () => {
  it('writes 12:00 p.m. as noon (UIC style), like 12 p.m.', () => {
    const { changes } = runMockRules('Lunch at 12:00pm and 12:00 PM, done by 1:00pm.', ['content'])
    expect(changes.map((c) => c.rewritten_text)).toEqual(['noon', 'noon', '1 p.m.'])
  })
})

describe('ws2Adapter robustness', () => {
  it('falls back to the configured rulesets when the API lists none we know', () => {
    expect(adaptRules({ rulesets: [{ ruleset_id: 'legal' }] }).map((r) => r.ruleset_id)).toEqual(RULESET_ORDER)
  })

  it('ignores unknown / duplicate audiences instead of mapping them all to Students', () => {
    const a = adaptAudiences({ audiences: [
      { audience_id: 'students', target_grade_level: 8 }, { audience_id: 'alumni' }, { audience_id: 'STAFF' }, { audience_id: 'students' },
    ] })
    expect(a.map((x) => x.id)).toEqual(['Students', 'Staff'])
    expect(adaptAudiences({ audiences: [{ audience_id: 'donors' }] }).map((x) => x.id)).toEqual(['Students', 'Faculty', 'Staff'])
  })
})

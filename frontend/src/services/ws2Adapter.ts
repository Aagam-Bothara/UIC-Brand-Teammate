/**
 * Adapters between the frontend types and Workstream 2's rule-engine API
 * (backend/api/rules_routes.py): GET /api/rules, GET /api/audiences, POST /api/rules/check.
 */
import { AUDIENCES, RULESET_ORDER, RULESETS } from '../config/rulesets'
import type { Audience, AudienceInfo, Channel, ComplianceStatus, Issue, RulesetId, RulesetInfo, Scores } from '../types/api'

export const AUDIENCE_TO_API: Record<Audience, string> = { Students: 'students', Faculty: 'faculty', Staff: 'staff' }
export const CHANNEL_TO_API: Record<Channel, string> = { Email: 'email', Website: 'website', 'Social Media': 'social_media' }
const STATUS_FROM_API: Record<string, ComplianceStatus> = {
  Approved: 'Approved',
  'Minor Revisions': 'Minor Revisions Needed',
  'Major Revisions': 'Major Revisions Needed',
}

export const audienceFromApi = (a: string): Audience =>
  (Object.keys(AUDIENCE_TO_API) as Audience[]).find((k) => AUDIENCE_TO_API[k] === a.toLowerCase()) ?? 'Students'

export const statusFromApi = (s: string): ComplianceStatus => STATUS_FROM_API[s] ?? (s as ComplianceStatus)

/** WS2 offsets are Python code-point indexes; JS strings index UTF-16 units (emoji count as 2). */
export function codePointToUtf16(text: string): (i: number) => number {
  const map = [0]
  let u = 0
  for (const ch of text) {
    u += ch.length
    map.push(u)
  }
  return (i) => map[i] ?? text.length
}

interface ApiRuleset extends Partial<RulesetInfo> {
  ruleset_id: RulesetId
}

/** GET /api/rules → RulesetInfo[] in SPEC order. Keeps the short UI names; takes colors/counts from the API. */
export function adaptRules(data: unknown): RulesetInfo[] {
  const list = (Array.isArray(data) ? data : (data as { rulesets?: ApiRuleset[] })?.rulesets) as ApiRuleset[] | undefined
  if (!list?.length) return RULESET_ORDER.map((id) => RULESETS[id])
  const byId = new Map(list.filter((r) => r && typeof r === 'object').map((r) => [r.ruleset_id, r]))
  const known = RULESET_ORDER.filter((id) => byId.has(id))
  // Nothing we recognise (renamed ids, wrong payload): an empty Checks panel would block analysis.
  if (!known.length) return RULESET_ORDER.map((id) => RULESETS[id])
  return known.map((id) => {
    const r = byId.get(id)!
    const base = RULESETS[id]
    return {
      ...base,
      description: r.description || base.description,
      highlight_color: r.highlight_color || base.highlight_color,
      enabled: r.enabled ?? true,
      rule_count: r.rule_count ?? base.rule_count,
    }
  })
}

/** GET /api/audiences → AudienceInfo[] (descriptions from local config). */
export function adaptAudiences(data: unknown): AudienceInfo[] {
  const list = (data as { audiences?: { audience_id: string; label?: string; target_grade_level?: number }[] })?.audiences
  if (!Array.isArray(list) || !list.length) return AUDIENCES
  // Only the 3 SPEC audiences are supported; unknown ids (e.g. 'alumni') used to be mapped to
  // Students, producing duplicate "Students" segments. Skip them and de-duplicate instead.
  const out: AudienceInfo[] = []
  for (const a of list) {
    const local = AUDIENCES.find((x) => typeof a?.audience_id === 'string' && AUDIENCE_TO_API[x.id] === a.audience_id.toLowerCase())
    if (!local || out.some((x) => x.id === local.id)) continue
    const target = typeof a.target_grade_level === 'number' && Number.isFinite(a.target_grade_level) ? a.target_grade_level : local.reading_level_target
    out.push({ id: local.id, label: a.label || local.label, description: local.description, reading_level_target: target })
  }
  return out.length ? out : AUDIENCES
}

interface ApiIssue {
  issue_id: string
  rule_id: string
  ruleset_id: RulesetId
  rule_name?: string
  severity: Issue['severity']
  message: string
  matched_text: string
  start: number
  end: number
  scope?: 'span' | 'document'
  suggestion?: string | null
  guideline_url?: string | null
  guideline_title?: string | null
}

/** POST /api/rules/check response → frontend issues + scores (offsets converted to UTF-16). */
export function adaptCheck(text: string, data: {
  analysis: { audience: string; issues: ApiIssue[]; reading_level: { grade_level: number; target_grade: number } }
  scores: { brand_score: number; accessibility_score: number; total_issues: number; status: string }
}): { issues: Issue[]; scores: Scores } {
  const conv = codePointToUtf16(text)
  const { analysis: a, scores: s } = data
  return {
    issues: a.issues.map((i) => ({
      issue_id: i.issue_id, ruleset: i.ruleset_id, rule_id: i.rule_id, rule_name: i.rule_name, severity: i.severity,
      message: i.message, start: conv(i.start), end: conv(i.end), excerpt: i.matched_text, scope: i.scope ?? 'span',
      suggestion: i.suggestion ?? null, guideline_url: i.guideline_url ?? null, guideline_title: i.guideline_title ?? null,
    })),
    scores: {
      brand: s.brand_score,
      accessibility: s.accessibility_score,
      reading_level: { grade: a.reading_level.grade_level, target: a.reading_level.target_grade, audience: audienceFromApi(a.audience) },
      total_issues: s.total_issues,
      status: statusFromApi(s.status),
    },
  }
}

/**
 * Validation for data whose shape we don't control: values restored from localStorage (may be
 * corrupt, from an older app version, or hand-edited) and backend responses (WS2 vocabulary such as
 * 'Minor Revisions' / 'students'). Each sanitizer returns a well-formed value, or null when the input
 * is unusable — so a bad value can never crash the app on load.
 */
import { AUDIENCES, CHANNELS, READING_LEVEL_TARGET, RULESET_ORDER } from '../config/rulesets'
import type {
  Audience,
  AnalyzeResponse,
  Change,
  Channel,
  ChatMessage,
  ComplianceStatus,
  GuidelineChunk,
  Issue,
  RulesetId,
  Scores,
  Severity,
} from '../types/api'
import { applyChanges, type Decisions } from './changes'
import { fleschKincaidGrade } from './readability'
import { classify, computeScores, SEVERITY_DEDUCTION } from './scoring'

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)
const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const optStr = (v: unknown): string | null => (typeof v === 'string' ? v : null)
/** Compare vocab loosely: "social_media" ≈ "Social Media", "students" ≈ "Students". */
const key = (v: string) => v.toLowerCase().replace(/[\s_-]+/g, ' ').trim()

export const isRulesetId = (v: unknown): v is RulesetId => RULESET_ORDER.includes(v as RulesetId)

/** Known ruleset ids, de-duplicated, in SPEC order. Null when not an array. */
export function sanitizeRulesetIds(v: unknown): RulesetId[] | null {
  if (!Array.isArray(v)) return null
  return RULESET_ORDER.filter((id) => v.includes(id))
}

export function sanitizeAudience(v: unknown): Audience | null {
  if (typeof v !== 'string') return null
  return AUDIENCES.find((a) => key(a.id) === key(v))?.id ?? null
}

export function sanitizeChannel(v: unknown): Channel | null {
  if (typeof v !== 'string') return null
  return CHANNELS.find((c) => key(c.id) === key(v))?.id ?? null
}

const STATUS: Record<string, ComplianceStatus> = {
  approved: 'Approved',
  'minor revisions': 'Minor Revisions Needed',
  'minor revisions needed': 'Minor Revisions Needed',
  'major revisions': 'Major Revisions Needed',
  'major revisions needed': 'Major Revisions Needed',
}
export const sanitizeStatus = (v: unknown): ComplianceStatus | null => (typeof v === 'string' ? STATUS[key(v)] ?? null : null)

function sanitizeSeverity(v: unknown): Severity | null {
  const s = typeof v === 'string' ? v.toLowerCase() : ''
  return s in SEVERITY_DEDUCTION ? (s as Severity) : null
}

const int = (v: unknown, fallback: number) => (Number.isInteger(v) ? (v as number) : fallback)

function sanitizeIssue(v: unknown): Issue | null {
  if (!isObj(v) || typeof v.issue_id !== 'string' || !isRulesetId(v.ruleset)) return null
  const severity = sanitizeSeverity(v.severity)
  if (!severity) return null
  const scope = v.scope === 'document' || v.scope === 'span' ? v.scope : undefined
  return {
    ...v,
    issue_id: v.issue_id,
    ruleset: v.ruleset,
    rule_id: str(v.rule_id, v.ruleset),
    severity,
    message: str(v.message),
    start: int(v.start, 0),
    end: int(v.end, 0),
    excerpt: str(v.excerpt),
    ...(scope ? { scope } : {}),
  } as Issue
}

function sanitizeChange(v: unknown): Change | null {
  if (!isObj(v) || typeof v.change_id !== 'string' || !isRulesetId(v.ruleset)) return null
  if (!Number.isInteger(v.original_start) || !Number.isInteger(v.original_end) || typeof v.rewritten_text !== 'string') return null
  return {
    ...v,
    change_id: v.change_id,
    ruleset: v.ruleset,
    original_start: v.original_start as number,
    original_end: v.original_end as number,
    original_text: str(v.original_text),
    rewritten_text: v.rewritten_text,
    explanation: str(v.explanation),
    issue_ids: Array.isArray(v.issue_ids) ? v.issue_ids.filter((x): x is string => typeof x === 'string') : [],
  } as Change
}

const isGuideline = (v: unknown): v is GuidelineChunk => isObj(v) && typeof v.text === 'string'

function sanitizeScores(v: unknown, issues: Issue[], original: string, audience: Audience): Scores {
  const computed = computeScores(issues)
  const s = isObj(v) ? v : {}
  const brand = num(s.brand) ?? computed.brand
  const accessibility = num(s.accessibility) ?? computed.accessibility
  const total = Number.isInteger(s.total_issues) ? (s.total_issues as number) : issues.length
  const rl = isObj(s.reading_level) ? s.reading_level : {}
  return {
    brand,
    accessibility,
    total_issues: total,
    status: sanitizeStatus(s.status) ?? classify(brand, accessibility, total),
    reading_level: {
      grade: num(rl.grade) ?? fleschKincaidGrade(original),
      target: num(rl.target) ?? READING_LEVEL_TARGET[audience],
      audience: sanitizeAudience(rl.audience) ?? audience,
    },
  }
}

/** A usable AnalyzeResponse (missing optional fields filled, invalid items dropped) or null. */
export function sanitizeAnalysis(v: unknown): AnalyzeResponse | null {
  if (!isObj(v) || typeof v.original !== 'string' || !Array.isArray(v.changes)) return null
  const original = v.original
  const changes = v.changes.map(sanitizeChange).filter((c): c is Change => c !== null)
  const issues = (Array.isArray(v.issues) ? v.issues : []).map(sanitizeIssue).filter((i): i is Issue => i !== null)
  const audience = sanitizeAudience(v.audience) ?? 'Students'
  const rulesets =
    sanitizeRulesetIds(v.rulesets) ?? RULESET_ORDER.filter((id) => changes.some((c) => c.ruleset === id) || issues.some((i) => i.ruleset === id))
  return {
    ...v,
    analysis_id: str(v.analysis_id),
    original,
    rewritten: typeof v.rewritten === 'string' ? v.rewritten : applyChanges(original, changes, () => true),
    changes,
    issues,
    scores: sanitizeScores(v.scores, issues, original, audience),
    guidelines: Array.isArray(v.guidelines) ? v.guidelines.filter(isGuideline) : [],
    audience,
    channel: sanitizeChannel(v.channel) ?? 'Email',
    rulesets,
    model_used: str(v.model_used),
    latency_ms: num(v.latency_ms) ?? 0,
  } as AnalyzeResponse
}

/** Accept/reject decisions restricted to changes that exist in `analysis`. */
export function sanitizeDecisions(v: unknown, analysis: AnalyzeResponse | null): Decisions | null {
  if (!isObj(v)) return null
  const ids = new Set(analysis?.changes.map((c) => c.change_id) ?? [])
  const out: Decisions = {}
  for (const [id, d] of Object.entries(v)) if (ids.has(id) && (d === 'accepted' || d === 'rejected')) out[id] = d
  return out
}

let restoredSeq = 0
export function sanitizeChat(v: unknown): ChatMessage[] | null {
  if (!Array.isArray(v)) return null
  return v.flatMap((m): ChatMessage[] => {
    if (!isObj(m) || (m.role !== 'user' && m.role !== 'assistant') || typeof m.content !== 'string') return []
    return [{
      ...m,
      id: optStr(m.id) ?? `restored-${++restoredSeq}`,
      role: m.role,
      content: m.content,
      created_at: str(m.created_at),
      ...(Array.isArray(m.guidelines) ? { guidelines: m.guidelines.filter(isGuideline) } : {}),
    } as ChatMessage]
  })
}

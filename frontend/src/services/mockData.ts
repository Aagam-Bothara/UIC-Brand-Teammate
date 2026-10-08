/**
 * Mock backend for Workstream 4 (Task 4.2) until /api/analyze and /api/llm/refine are live.
 *
 * `mockAnalyze` runs a small set of demo rules over ANY input text and returns a response in the
 * real AnalyzeResponse shape (layered, non-overlapping changes with correct offsets), so every
 * component can be built and demoed against realistic data. Replace with the real API by setting
 * VITE_USE_MOCKS=false.
 */
import { READING_LEVEL_TARGET } from '../config/rulesets'
import { applyChanges } from '../lib/changes'
import { fleschKincaidGrade } from '../lib/readability'
import { computeScores } from '../lib/scoring'
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  Change,
  GuidelineChunk,
  Issue,
  RefineRequest,
  RefineResponse,
  RulesetId,
  Severity,
} from '../types/api'

const URL_NAME = 'https://brand.uic.edu/messaging/name-and-boilerplate/'
const URL_EDITORIAL = 'https://brand.uic.edu/messaging/editorial-and-style-guide/'
const URL_TONE = 'https://brand.uic.edu/messaging/voice-and-tone/'
const URL_AUDIENCE = 'https://brand.uic.edu/messaging/brand-strategy/'

export const SAMPLE_TEXT = `Hey guys!

The University of Illinois at Chicago Career Services office will host the Fall Career Fair on March 5th from 12pm to 4pm in the Student Center East. In order to prepare, students should utilize the resume review sessions prior to the event. Over 100 employers will be there and it's going to be AMAZING!!

Click here to register ASAP. For more info, email careers@uic.edu.`

interface MockRule {
  rule_id: string
  ruleset: RulesetId
  severity: Severity
  pattern: RegExp
  replace: (m: RegExpExecArray) => string
  message: string
  explanation: string
  guideline_title: string
  guideline_url: string
}

const ACRONYMS = new Set(['UIC', 'ASAP', 'NCAA', 'FAQ', 'USA', 'PDF', 'URL', 'HTML', 'CEO', 'GPA', 'STEM'])

const RULES: MockRule[] = [
  {
    rule_id: 'brand-001', ruleset: 'brand', severity: 'high',
    pattern: /University of Illinois at Chicago/g,
    replace: () => 'University of Illinois Chicago',
    message: 'Use the official university name.',
    explanation: 'The official name is “University of Illinois Chicago” — never use “at” or a hyphen between Illinois and Chicago.',
    guideline_title: 'Name and boilerplate — Nomenclature', guideline_url: URL_NAME,
  },
  {
    rule_id: 'brand-002', ruleset: 'brand', severity: 'low',
    pattern: /\be-mail\b/gi,
    replace: (m) => (m[0][0] === 'E' ? 'Email' : 'email'),
    message: 'Write “email” without a hyphen.',
    explanation: 'UIC editorial style uses “email,” not “e-mail.”',
    guideline_title: 'Editorial and style guide', guideline_url: URL_EDITORIAL,
  },
  {
    rule_id: 'acc-001', ruleset: 'accessibility', severity: 'high',
    pattern: /\b[Cc]lick here\b/g,
    replace: (m) => (m[0][0] === 'C' ? 'Register online' : 'register online'),
    message: 'Link text should describe its destination.',
    explanation: 'Screen reader users often jump between links; “click here” gives no context. Describe the action instead.',
    guideline_title: 'Editorial and style guide — Links', guideline_url: URL_EDITORIAL,
  },
  {
    rule_id: 'acc-002', ruleset: 'accessibility', severity: 'medium',
    pattern: /\b[A-Z]{4,}\b/g,
    replace: (m) => m[0].toLowerCase(),
    message: 'Avoid all-caps words for emphasis.',
    explanation: 'All-caps text is harder to read and some screen readers spell it letter by letter.',
    guideline_title: 'Editorial and style guide — Capitalization', guideline_url: URL_EDITORIAL,
  },
  {
    rule_id: 'content-001', ruleset: 'content', severity: 'medium',
    pattern: /\b(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})(st|nd|rd|th)\b/g,
    replace: (m) => `${m[1]} ${m[2]}`,
    message: 'Drop ordinal suffixes from dates.',
    explanation: 'Write dates as “March 5,” not “March 5th.”',
    guideline_title: 'Editorial and style guide — Dates', guideline_url: URL_EDITORIAL,
  },
  {
    rule_id: 'content-002', ruleset: 'content', severity: 'low',
    pattern: /\b(\d{1,2})(?::(\d{2}))?\s?(am|pm|AM|PM)\b/g,
    replace: (m) => {
      if (m[1] === '12' && (!m[2] || m[2] === '00') && /pm/i.test(m[3])) return 'noon'
      return `${m[1]}${m[2] && m[2] !== '00' ? `:${m[2]}` : ''} ${m[3].toLowerCase()[0]}.m.`
    },
    message: 'Use UIC time style.',
    explanation: 'Use “a.m.” and “p.m.” with a space and periods, omit “:00,” and write “noon” instead of 12 p.m.',
    guideline_title: 'Editorial and style guide — Times', guideline_url: URL_EDITORIAL,
  },
  {
    rule_id: 'content-003', ruleset: 'content', severity: 'low',
    pattern: /!{2,}/g,
    replace: () => '!',
    message: 'Use at most one exclamation point.',
    explanation: 'Multiple exclamation points read as informal and reduce credibility.',
    guideline_title: 'Editorial and style guide — Punctuation', guideline_url: URL_EDITORIAL,
  },
  {
    rule_id: 'read-001', ruleset: 'reading_level', severity: 'low',
    pattern: /\b(utilize|in order to|prior to|approximately|commence|facilitate)\b/gi,
    replace: (m) => {
      const map: Record<string, string> = {
        utilize: 'use', 'in order to': 'to', 'prior to': 'before', approximately: 'about', commence: 'start', facilitate: 'help',
      }
      const out = map[m[0].toLowerCase()]
      return m[0][0] === m[0][0].toUpperCase() ? out[0].toUpperCase() + out.slice(1) : out
    },
    message: 'Use a simpler word.',
    explanation: 'Plain words lower the reading level and make the message faster to scan.',
    guideline_title: 'Voice and tone', guideline_url: URL_TONE,
  },
  {
    rule_id: 'tone-001', ruleset: 'audience_tone', severity: 'medium',
    pattern: /\b(Hey|Hi) guys\b/g,
    replace: () => 'Hello, everyone',
    message: 'Use an inclusive, welcoming greeting.',
    explanation: '“Guys” isn’t gender-neutral. A warm, inclusive greeting fits UIC’s voice.',
    guideline_title: 'Voice and tone', guideline_url: URL_TONE,
  },
  {
    rule_id: 'tone-002', ruleset: 'audience_tone', severity: 'low',
    pattern: /\bASAP\b/g,
    replace: () => 'today',
    message: 'Replace jargon with a clear, specific ask.',
    explanation: 'A concrete call to action (“register today”) is clearer than an acronym.',
    guideline_title: 'Brand strategy — Audiences', guideline_url: URL_AUDIENCE,
  },
]

let counter = 0
const nextId = (prefix: string) => `${prefix}-${(++counter).toString(36)}`

/** Run the demo rules for the selected rulesets; returns non-overlapping issues + changes. */
export function runMockRules(text: string, rulesets: RulesetId[]): { issues: Issue[]; changes: Change[] } {
  type Hit = { rule: MockRule; start: number; end: number; original: string; rewritten: string }
  const hits: Hit[] = []
  for (const rule of RULES) {
    if (!rulesets.includes(rule.ruleset)) continue
    // Always global (exec loop) and never stuck on a zero-length match.
    const re = new RegExp(rule.pattern.source, rule.pattern.flags.includes('g') ? rule.pattern.flags : `${rule.pattern.flags}g`)
    let m: RegExpExecArray | null
    while ((m = re.exec(text)) !== null) {
      if (m[0] === '') {
        re.lastIndex++
        continue
      }
      if (rule.rule_id === 'acc-002' && ACRONYMS.has(m[0])) continue
      const rewritten = rule.replace(m)
      if (rewritten !== m[0]) hits.push({ rule, start: m.index, end: m.index + m[0].length, original: m[0], rewritten })
    }
  }
  hits.sort((a, b) => a.start - b.start || b.end - a.end)
  const issues: Issue[] = []
  const changes: Change[] = []
  let cursor = -1
  for (const h of hits) {
    if (h.start < cursor) continue
    cursor = h.end
    const issue_id = nextId('iss')
    issues.push({
      issue_id, ruleset: h.rule.ruleset, rule_id: h.rule.rule_id, severity: h.rule.severity,
      message: h.rule.message, start: h.start, end: h.end, excerpt: h.original,
      suggestion: h.rewritten, guideline_url: h.rule.guideline_url, guideline_title: h.rule.guideline_title,
    })
    changes.push({
      change_id: nextId('chg'), ruleset: h.rule.ruleset, original_start: h.start, original_end: h.end,
      original_text: h.original, rewritten_text: h.rewritten, explanation: h.rule.explanation,
      issue_ids: [issue_id], guideline_url: h.rule.guideline_url, guideline_title: h.rule.guideline_title,
    })
  }
  return { issues, changes }
}

export const MOCK_GUIDELINES: GuidelineChunk[] = [
  {
    chunk_id: 'name-boilerplate-001', score: 0.82, source_id: 'name-boilerplate', category: 'name',
    source_title: 'Name and boilerplate', source_url: URL_NAME, section: 'Nomenclature',
    text: '**Official full name:** University of Illinois Chicago\n\n**Informal name/acronym:** UIC\n\n- Use the full name of the university wherever possible.\n- Do not use a hyphen or “at” between Illinois and Chicago.',
  },
  {
    chunk_id: 'editorial-style-032', score: 0.74, source_id: 'editorial-style', category: 'editorial',
    source_title: 'Editorial and style guide', source_url: URL_EDITORIAL, section: 'D-E-F',
    text: '**dates:** Always use Arabic figures, without st, nd, rd or th. Capitalize months and abbreviate Jan., Feb., Aug., Sept., Oct., Nov. and Dec. when used with a specific date.',
  },
  {
    chunk_id: 'voice-tone-014', score: 0.68, source_id: 'voice-tone', category: 'tone',
    source_title: 'Voice and tone', source_url: URL_TONE, section: 'Flexing our tone',
    text: 'Our voice stays consistent, but our tone flexes for each audience. With students we are direct, energetic and encouraging.',
  },
]

export function mockAnalyze(req: AnalyzeRequest, guidelines: GuidelineChunk[] = MOCK_GUIDELINES): AnalyzeResponse {
  const { issues, changes } = runMockRules(req.text, req.rulesets)
  const rewritten = applyChanges(req.text, changes, () => true)
  const target = READING_LEVEL_TARGET[req.audience]
  const grade = fleschKincaidGrade(req.text)
  const readingIssues: Issue[] =
    req.rulesets.includes('reading_level') && grade > target
      ? [{
          issue_id: nextId('iss'), ruleset: 'reading_level', rule_id: 'read-grade', severity: grade > target + 3 ? 'medium' : 'low',
          message: `Reading level is grade ${grade}; target for ${req.audience} is grade ${target}.`,
          start: 0, end: 0, excerpt: '', scope: 'document', suggestion: 'Shorten sentences and use simpler words.',
          guideline_url: URL_TONE, guideline_title: 'Voice and tone',
        }]
      : []
  const allIssues = [...issues, ...readingIssues]
  return {
    analysis_id: nextId('ana'),
    original: req.text,
    rewritten,
    changes,
    issues: allIssues,
    scores: { ...computeScores(allIssues), reading_level: { grade, target, audience: req.audience } },
    guidelines,
    audience: req.audience,
    channel: req.channel,
    rulesets: req.rulesets,
    model_used: 'mock',
    latency_ms: 0,
  }
}

/** First ~280 chars of a chunk without its "# Title — Section" header, cut at a word boundary. */
function excerpt(text: string, max = 280): string {
  const body = text.replace(/^#.*\n+/, '').trim()
  if (body.length <= max) return body
  const cut = body.slice(0, max)
  return `${cut.slice(0, Math.max(cut.lastIndexOf(' '), max - 40)).trimEnd()}…`
}

/** Markdown blockquote: prefix every line (including blank ones) so multi-paragraph quotes stay together. */
const quote = (text: string) => text.split('\n').map((l) => (l ? `> ${l}` : '>')).join('\n')

/** Canned chat behaviour for FR-11 until /api/llm/refine is live. */
export function mockRefine(req: RefineRequest, guidelines: GuidelineChunk[] = []): RefineResponse {
  const msg = req.message.toLowerCase()
  const top = guidelines[0]
  const cite = top ? `\n\nFrom the UIC ${top.source_title}${top.section ? ` (${top.section})` : ''}:\n${quote(excerpt(top.text))}\n\nSource: ${top.source_url}` : ''
  if (/\b(why|explain|reason)\b/.test(msg)) {
    return { reply: `Each change is tied to a UIC guideline — click any highlighted change to see the rule and a link to the source.${cite}`, guidelines }
  }
  if (/\b(formal|casual|shorter|concise|friendlier|simpler)\b/.test(msg)) {
    return { reply: 'In the live app this re-runs the rewrite with your request. In mock mode the rewrite stays the same — try toggling rulesets to see progressive reveal.', guidelines }
  }
  return { reply: `Here’s what the UIC brand guidelines say that’s most relevant to your question.${cite || ' (No matching guideline found.)'}`, guidelines }
}

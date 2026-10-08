/**
 * Shared API types for the UIC Brand Teammate frontend (Task 4.2).
 *
 * Mirrors docs/API_CONTRACT.md ("Analyze API" section) and SPEC 1:
 * 5 rulesets, 3 audiences, 3 channels, layered edits for progressive reveal,
 * brand + accessibility scores with status classification.
 */

export type RulesetId = 'brand' | 'accessibility' | 'content' | 'reading_level' | 'audience_tone'
export type Audience = 'Students' | 'Faculty' | 'Staff'
export type Channel = 'Email' | 'Website' | 'Social Media'
export type Severity = 'high' | 'medium' | 'low'
/** Display form. WS2's API returns 'Approved' | 'Minor Revisions' | 'Major Revisions'; services/api.ts maps it. */
export type ComplianceStatus = 'Approved' | 'Minor Revisions Needed' | 'Major Revisions Needed'
export type GuidelineCategory = 'name' | 'tone' | 'audience' | 'editorial'

/** GET /api/rules */
export interface RulesetInfo {
  ruleset_id: RulesetId
  ruleset_name: string
  description: string
  highlight_color: string
  enabled: boolean
  rule_count: number
}

/** GET /api/audiences */
export interface AudienceInfo {
  id: Audience
  label: string
  description: string
  reading_level_target: number
}

/** POST /api/analyze request */
export interface AnalyzeRequest {
  text: string
  audience: Audience
  channel: Channel
  rulesets: RulesetId[]
}

/** A problem found in the ORIGINAL text. Offsets are [start, end) character indexes into `original`. */
export interface Issue {
  issue_id: string
  ruleset: RulesetId
  rule_id: string
  severity: Severity
  message: string
  start: number
  end: number
  excerpt: string
  suggestion?: string | null
  guideline_url?: string | null
  guideline_title?: string | null
  /** WS2: 'document' issues (e.g. overall reading level) span the whole text — list them, don't highlight. */
  scope?: 'span' | 'document'
  /** WS2 human-readable rule name, e.g. "Gendered language". */
  rule_name?: string
}

/**
 * One layered edit (SPEC "Reveal Mechanics: layered edits, pre-generate, toggle visibility").
 * Replaces original[original_start, original_end) with `rewritten_text`. Changes never overlap.
 * An insertion has original_start === original_end; a deletion has rewritten_text === ''.
 */
export interface Change {
  change_id: string
  ruleset: RulesetId
  original_start: number
  original_end: number
  original_text: string
  rewritten_text: string
  explanation: string
  issue_ids: string[]
  guideline_url?: string | null
  guideline_title?: string | null
}

/** Excerpt from the UIC brand guidelines (Workstream 1 RAG, see docs/RAG_API.md). */
export interface GuidelineChunk {
  chunk_id: string
  text: string
  score: number
  source_id: string
  source_title: string
  source_url: string
  category: GuidelineCategory
  section: string | null
}

export interface ReadingLevel {
  grade: number
  target: number
  audience: Audience
}

export interface Scores {
  /** 0–100: starts at 100, high −10, medium −5, low −2 (max 3 deductions per rule) over brand + content + audience_tone issues (WS2). */
  brand: number
  /** 0–100: same deductions over accessibility + reading_level issues (WS2). */
  accessibility: number
  reading_level: ReadingLevel
  total_issues: number
  status: ComplianceStatus
}

/** POST /api/analyze response */
export interface AnalyzeResponse {
  analysis_id: string
  original: string
  /** Original with ALL changes applied. */
  rewritten: string
  changes: Change[]
  issues: Issue[]
  scores: Scores
  guidelines: GuidelineChunk[]
  audience: Audience
  channel: Channel
  rulesets: RulesetId[]
  model_used: string
  latency_ms: number
}

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  created_at: string
  /** Guideline excerpts the assistant reply drew on (shown as source links). */
  guidelines?: GuidelineChunk[]
  /** True when this assistant message reports a failed request. */
  error?: boolean
}

/** POST /api/llm/refine request (FR-11: selection, refinements, explanations, questions) */
export interface RefineRequest {
  message: string
  original: string
  current_text: string
  audience: Audience
  channel: Channel
  rulesets: RulesetId[]
  history: Pick<ChatMessage, 'role' | 'content'>[]
  analysis_id?: string | null
}

/** POST /api/llm/refine response. `analysis` is present when the request changed the rewrite. */
export interface RefineResponse {
  reply: string
  analysis?: AnalyzeResponse | null
  guidelines?: GuidelineChunk[]
}

/** Error shape surfaced to the UI by services/api.ts */
export interface ApiError {
  status: number | null
  message: string
  retryable: boolean
  /** True when the request was cancelled by the app (AbortSignal); not shown as an error. */
  cancelled?: boolean
}

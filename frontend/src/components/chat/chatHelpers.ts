import type { AnalyzeResponse, Audience, Channel, ChatMessage, GuidelineChunk } from '../../types/api'

/** Starter questions before a draft has been checked (generic fallback; see buildSuggestions). */
export const STYLE_SUGGESTIONS = [
  'How do I write the university’s name correctly?',
  'What tone works best for students?',
  'What should a UIC email always include?',
  'How should I format dates and times?',
]

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s)

export interface SuggestionContext {
  audience?: Audience
  channel?: Channel
  /** Issues still open after the currently applied changes (TextContext.openIssues). */
  openIssueCount?: number
}

const CHANNEL_NOUN: Record<Channel, string> = { Email: 'email', Website: 'web page', 'Social Media': 'social media post' }

/** One concrete next step that fits the channel. */
const CHANNEL_ACTION: Record<Channel, string> = {
  Email: 'Suggest a clear subject line for this email',
  Website: 'Add a clear call to action for the web page',
  'Social Media': 'Turn this into a short social post with one call to action',
}

/** Tone request that fits the audience (students: warmer; faculty/staff: more formal). */
const AUDIENCE_ACTION: Record<Audience, string> = {
  Students: 'Make it warmer and more energetic for students',
  Faculty: 'Make it more formal for faculty',
  Staff: 'Make it more concise and professional for staff',
}

/**
 * Suggested prompts that adapt to the session (FR-11). Before an analysis: UIC style questions for
 * the selected audience and channel. After one: explain a real change, then audience- and
 * channel-specific refinements, then a readiness check. The UI shows the first three.
 */
export function buildSuggestions(analysis: AnalyzeResponse | null, ctx: SuggestionContext = {}): string[] {
  const audience = ctx.audience ?? 'Students'
  const channel = ctx.channel ?? 'Email'
  if (!analysis) {
    return [
      'How do I write the university’s name correctly?',
      `What tone works best for ${audience.toLowerCase()}?`,
      `What should a UIC ${CHANNEL_NOUN[channel]} always include?`,
      'How should I format dates and times?',
    ]
  }
  const { changes } = analysis
  const out: string[] = []

  // Explain the most recognizable change: the university name, then accessibility, then any edit.
  const nameChange = changes.find((c) => /university of illinois/i.test(c.original_text))
  const accChange = changes.find((c) => c.ruleset === 'accessibility' && c.original_text.trim().length > 1)
  const anyChange = changes.find((c) => c.original_text.trim().length > 1)
  const explain = nameChange ?? accChange ?? anyChange
  if (explain === nameChange && nameChange) out.push('Why did you change the university name?')
  else if (explain) out.push(`Why did you change “${truncate(explain.original_text.trim(), 28)}”?`)

  out.push(AUDIENCE_ACTION[audience], CHANNEL_ACTION[channel])
  out.push((ctx.openIssueCount ?? 0) > 0 ? 'What still needs fixing before I send this?' : 'Is this ready to send?')
  return out
}

/** Hide suggestions the user already asked in this conversation. */
export function unaskedSuggestions(suggestions: string[], chat: ChatMessage[]): string[] {
  const asked = new Set(chat.filter((m) => m.role === 'user').map((m) => m.content.trim().toLowerCase()))
  return suggestions.filter((s) => !asked.has(s.toLowerCase()))
}

// ----------------------------------------------------------------------------- guideline sources

export interface GuidelineSource {
  title: string
  url: string
}

/** The four indexed UIC brand guideline pages (Workstream 1 RAG sources). */
const KNOWN_GUIDELINES: GuidelineSource[] = [
  { title: 'Name and boilerplate', url: 'https://brand.uic.edu/messaging/name-and-boilerplate/' },
  { title: 'Voice and tone', url: 'https://brand.uic.edu/messaging/voice-and-tone/' },
  { title: 'Brand strategy', url: 'https://brand.uic.edu/messaging/brand-strategy/' },
  { title: 'Editorial and style guide', url: 'https://brand.uic.edu/messaging/editorial-and-style-guide/' },
]

export const BRAND_GUIDELINES_URL = 'https://brand.uic.edu/'

/**
 * Guideline pages to cite under an assistant reply: explicit `guidelines` (if the message carries
 * them) plus any known guideline page named in the text. URLs already linked inline are skipped.
 */
export function guidelineSources(message: ChatMessage & { guidelines?: GuidelineChunk[] | null }): GuidelineSource[] {
  const seen = new Set<string>()
  const out: GuidelineSource[] = []
  const add = (s: GuidelineSource) => {
    const key = s.url.replace(/\/$/, '')
    if (seen.has(key) || message.content.includes(key)) return
    seen.add(key)
    out.push(s)
  }
  for (const g of message.guidelines ?? []) if (g.source_url) add({ title: g.source_title, url: g.source_url })
  const lower = message.content.toLowerCase()
  for (const g of KNOWN_GUIDELINES) if (lower.includes(g.title.toLowerCase())) add(g)
  return out.slice(0, 4)
}

// ----------------------------------------------------------------------------- message helpers

/** Failed refine() calls are flagged `error: true` by TextContext (older persisted messages: "Sorry — " prefix). */
export const isErrorReply = (m: Pick<ChatMessage, 'role' | 'content' | 'error'>) =>
  m.role === 'assistant' && (m.error === true || /^Sorry\s+[—-]/.test(m.content))

export function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export const MAX_MESSAGE_LENGTH = 1000
/** Show the character counter once the draft reaches this length. */
export const COUNTER_THRESHOLD = 800

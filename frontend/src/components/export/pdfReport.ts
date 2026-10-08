/**
 * Task 4.9 — client-side PDF compliance report (FR-12).
 *
 * `buildReportData` turns app state into a plain, serialisable ReportData; `buildReportPdf` lays it
 * out with jsPDF (lazy-imported so jsPDF stays out of the main bundle) and returns the document.
 */
import type { jsPDF } from 'jspdf'
import { isChangeApplied, normalizeChanges, type Decisions } from '../../lib/changes'
import type { AnalyzeResponse, Audience, Channel, ComplianceStatus, Issue, RulesetId, RulesetInfo, Scores, Severity } from '../../types/api'
import { MANUAL_REVIEW_MINUTES, SCORE_CAPTIONS, SEVERITY_META, STATUS_META, estimateCurrentGrade, isDocumentIssue } from '../compliance/meta'

export const REPORT_TITLE = 'UIC Brand Teammate — Compliance Report'

/** Official full-color logo (white backgrounds only — DESIGN.md). 700 × 146 px. */
export const LOGO_PATH = 'brand/uic-logo-primary.png'
const LOGO_ASPECT = 146 / 700

export interface ReportChange {
  ruleset: string
  color: string
  before: string
  after: string
  explanation: string
  guidelineTitle?: string | null
  guidelineUrl?: string | null
}

export interface ReportIssue {
  ruleset: string
  color: string
  severity: Severity
  message: string
  ruleName?: string | null
  excerpt?: string | null
  suggestion?: string | null
  guidelineTitle?: string | null
  guidelineUrl?: string | null
}

export interface ReportData {
  generatedAt: Date
  audience: Audience
  channel: Channel
  rulesets: string[]
  before: Scores
  now: Scores
  /** Estimated reading grade of the improved text. */
  readingNow: number
  issuesFound: number
  text: string
  appliedChanges: ReportChange[]
  openIssues: ReportIssue[]
  sources: { title: string; url: string }[]
  /** PNG data URL for the header logo; `undefined` = fetch it, `null` = no logo. */
  logo?: string | null
}

interface BuildReportDataInput {
  analysis: AnalyzeResponse
  currentText: string
  currentScores: Scores
  openIssues: Issue[]
  revealed: ReadonlySet<RulesetId>
  decisions: Decisions
  rulesetById: Record<RulesetId, RulesetInfo>
  generatedAt?: Date
}

const ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 }

export function buildReportData(input: BuildReportDataInput): ReportData {
  const { analysis, currentText, currentScores, openIssues, revealed, decisions, rulesetById } = input
  const name = (id: RulesetId) => rulesetById[id]?.ruleset_name ?? id
  const color = (id: RulesetId) => rulesetById[id]?.highlight_color ?? '#001E62'

  // Same (sorted, non-overlapping) changes the comparison view shows and applies.
  const applied = normalizeChanges(analysis.original, analysis.changes).filter((c) => isChangeApplied(c, revealed, decisions))

  const sources = new Map<string, string>()
  const addSource = (url?: string | null, title?: string | null) => {
    if (url && !sources.has(url)) sources.set(url, title || url)
  }
  for (const g of analysis.guidelines) addSource(g.source_url, g.source_title)
  for (const c of applied) addSource(c.guideline_url, c.guideline_title)
  for (const i of openIssues) addSource(i.guideline_url, i.guideline_title)

  return {
    generatedAt: input.generatedAt ?? new Date(),
    audience: analysis.audience,
    channel: analysis.channel,
    rulesets: analysis.rulesets.map(name),
    before: analysis.scores,
    now: currentScores,
    readingNow: estimateCurrentGrade(analysis, currentText),
    issuesFound: analysis.issues.length,
    text: currentText,
    appliedChanges: applied.map((c) => ({
      ruleset: name(c.ruleset),
      color: color(c.ruleset),
      before: c.original_text,
      after: c.rewritten_text,
      explanation: c.explanation,
      guidelineTitle: c.guideline_title,
      guidelineUrl: c.guideline_url,
    })),
    openIssues: [...openIssues]
      .sort((a, b) => ORDER[a.severity] - ORDER[b.severity])
      .map((i) => ({
        ruleset: name(i.ruleset),
        color: color(i.ruleset),
        severity: i.severity,
        message: i.message,
        ruleName: i.rule_name,
        excerpt: isDocumentIssue(i) ? null : i.excerpt,
        suggestion: i.suggestion,
        guidelineTitle: i.guideline_title,
        guidelineUrl: i.guideline_url,
      })),
    sources: [...sources].map(([url, title]) => ({ url, title })),
  }
}

/* ------------------------------------------------------------------ PDF layout */

type RGB = [number, number, number]
const NAVY: RGB = [0, 30, 98]
const STEEL: RGB = [52, 51, 51]
const MUTED: RGB = [105, 105, 105]
const RULE: RGB = [225, 222, 215]
const LINK: RGB = [0, 61, 165]

const PAGE_W = 612 // US Letter, points
const PAGE_H = 792
const M = 54
const CONTENT_W = PAGE_W - M * 2
const BOTTOM = PAGE_H - 56

const hexToRgb = (hex: string): RGB => {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
const tint = (c: RGB, a: number): RGB => c.map((v) => Math.round(v * a + 255 * (1 - a))) as RGB

const PDF_REPLACEMENTS: [RegExp, string][] = [
  [/[‘’‚′]/g, "'"],
  [/[“”„″]/g, '"'],
  [/[–—−]/g, '-'],
  [/…/g, '...'],
  [/→/g, '->'],
  [/←/g, '<-'],
  [/≈/g, '~'],
  [/≥/g, '>='],
  [/≤/g, '<='],
  [/[•●]/g, '·'],
  [/[   ]/g, ' '],
  [/\t/g, '    '],
  [/\r\n?/g, '\n'],
]

/**
 * jsPDF's built-in fonts only cover Latin-1; anything else is emitted as garbage. Map common
 * typography to ASCII and strip what can't be represented.
 */
export function toPdfText(s: string): string {
  let out = s
  for (const [re, rep] of PDF_REPLACEMENTS) out = out.replace(re, rep)
  return Array.from(out, (ch) => {
    if (ch.codePointAt(0)! <= 0xff) return ch
    const base = ch.normalize('NFKD').replace(/[̀-ͯ]/g, '')
    return [...base].every((c) => c.codePointAt(0)! <= 0xff) ? base : ''
  }).join('')
}

function formatDate(d: Date): string {
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

const signed = (n: number, digits = 0) => (n > 0 ? '+' : '') + (digits ? n.toFixed(digits) : String(Math.round(n)))

class Writer {
  y = M
  private doc: jsPDF
  constructor(doc: jsPDF) {
    this.doc = doc
  }

  font(size: number, style: 'normal' | 'bold' | 'italic' = 'normal', color: RGB = STEEL) {
    this.doc.setFont('helvetica', style)
    this.doc.setFontSize(size)
    this.doc.setTextColor(...color)
  }

  newPage() {
    this.doc.addPage()
    this.font(8.5, 'bold', NAVY)
    this.doc.text(toPdfText(REPORT_TITLE), M, 30)
    this.doc.setDrawColor(...NAVY)
    this.doc.setLineWidth(0.8)
    this.doc.line(M, 38, PAGE_W - M, 38)
    this.y = 58
  }

  ensure(h: number) {
    if (this.y + h > BOTTOM) this.newPage()
  }

  /** Wrapped text block; each line gets its own page-break check. */
  para(text: string, opts: { size?: number; style?: 'normal' | 'bold' | 'italic'; color?: RGB; x?: number; width?: number; lh?: number } = {}) {
    const { size = 10, style = 'normal', color = STEEL, x = M, width = CONTENT_W - (x - M), lh = size * 1.45 } = opts
    this.font(size, style, color)
    const lines = this.doc.splitTextToSize(toPdfText(text), width) as string[]
    for (const line of lines) {
      this.ensure(lh)
      this.doc.text(line, x, this.y + size * 0.8)
      this.y += lh
    }
  }

  /** "Label: value" with the value wrapped beside the label. */
  field(label: string, value: string, x: number, opts: { color?: RGB } = {}) {
    const size = 9.5
    this.font(size, 'bold', MUTED)
    const lw = this.doc.getTextWidth(toPdfText(label)) + 6
    this.font(size, 'normal', opts.color ?? STEEL)
    const lines = this.doc.splitTextToSize(toPdfText(value), CONTENT_W - (x - M) - lw) as string[]
    lines.forEach((line, i) => {
      this.ensure(size * 1.45)
      if (i === 0) {
        this.font(size, 'bold', MUTED)
        this.doc.text(toPdfText(label), x, this.y + size * 0.8)
        this.font(size, 'normal', opts.color ?? STEEL)
      }
      this.doc.text(line, x + lw, this.y + size * 0.8)
      this.y += size * 1.45
    })
  }

  link(label: string, url: string, x: number, size = 9) {
    this.font(size, 'normal', LINK)
    const line = (this.doc.splitTextToSize(toPdfText(label), CONTENT_W - (x - M)) as string[])[0] ?? ''
    this.ensure(size * 1.5)
    this.doc.textWithLink(line, x, this.y + size * 0.8, { url })
    const w = this.doc.getTextWidth(line)
    this.doc.setDrawColor(...LINK)
    this.doc.setLineWidth(0.4)
    this.doc.line(x, this.y + size * 0.95, x + w, this.y + size * 0.95)
    this.y += size * 1.5
  }

  section(title: string, count?: number) {
    // Keep the heading with at least the start of its first entry (no orphaned headings).
    this.ensure(110)
    this.y += 14
    this.font(13, 'bold', NAVY)
    this.doc.text(toPdfText(count === undefined ? title : `${title} (${count})`), M, this.y + 10)
    this.y += 17
    this.doc.setDrawColor(...RULE)
    this.doc.setLineWidth(0.8)
    this.doc.line(M, this.y, PAGE_W - M, this.y)
    this.y += 10
  }

  dot(color: RGB, x: number, size = 9) {
    this.doc.setFillColor(...color)
    this.doc.circle(x + 3, this.y + size * 0.5, 3, 'F')
  }
}

function statusColor(s: ComplianceStatus): RGB {
  return hexToRgb(STATUS_META[s].color)
}

/** Fetch the logo as a data URL at export time; null if it can't be loaded (the report still works). */
export async function loadLogo(): Promise<string | null> {
  try {
    if (typeof fetch !== 'function' || typeof FileReader === 'undefined') return null
    const res = await fetch(`${import.meta.env.BASE_URL ?? '/'}${LOGO_PATH}`)
    if (!res.ok) return null
    const blob = await res.blob()
    if (!blob.type.startsWith('image/')) return null
    return await new Promise<string | null>((resolve) => {
      const r = new FileReader()
      r.onload = () => resolve(typeof r.result === 'string' ? r.result : null)
      r.onerror = () => resolve(null)
      r.readAsDataURL(blob)
    })
  } catch {
    return null
  }
}

/** Build the compliance report. Returns the jsPDF document (call `.save(filename)` to download). */
export async function buildReportPdf(data: ReportData): Promise<jsPDF> {
  const { jsPDF: JsPDF } = await import('jspdf')
  const doc = new JsPDF({ unit: 'pt', format: 'letter' })
  doc.setProperties({
    title: toPdfText(REPORT_TITLE),
    subject: 'UIC brand and accessibility compliance report',
    creator: 'UIC Brand Teammate',
  })
  const w = new Writer(doc)

  // Header: white band, official logo (full color, aspect preserved), title, thin navy rule.
  let top = 40
  const logo = data.logo === undefined ? await loadLogo() : data.logo
  if (logo) {
    const lw = 150
    try {
      doc.addImage(logo, 'PNG', M, top, lw, lw * LOGO_ASPECT)
      top += lw * LOGO_ASPECT + 22
    } catch {
      /* unreadable image: header without the logo */
    }
  }
  w.font(17, 'bold', NAVY)
  doc.text(toPdfText(REPORT_TITLE), M, top + 10)
  w.font(9.5, 'normal', MUTED)
  doc.text(toPdfText(`Generated ${formatDate(data.generatedAt)}  ·  Audience: ${data.audience}  ·  Channel: ${data.channel}`), M, top + 27)
  doc.setDrawColor(...NAVY)
  doc.setLineWidth(1.2)
  doc.line(M, top + 38, PAGE_W - M, top + 38)
  w.y = top + 52
  w.field('Rulesets checked:', data.rulesets.join(', ') || 'None', M)
  w.y += 8

  // Status box
  const { now, before } = data
  const meta = STATUS_META[now.status]
  const sc = statusColor(now.status)
  const statusChanged = before.status !== now.status
  const boxH = statusChanged ? 66 : 54
  w.ensure(boxH)
  doc.setFillColor(...tint(sc, 0.1))
  doc.roundedRect(M, w.y, CONTENT_W, boxH, 6, 6, 'F')
  doc.setFillColor(...sc)
  doc.rect(M, w.y, 4, boxH, 'F')
  w.font(8, 'bold', MUTED)
  doc.text('STATUS', M + 16, w.y + 16)
  w.font(14, 'bold', hexToRgb(meta.text))
  doc.text(toPdfText(now.status), M + 16, w.y + 33)
  w.font(9.5, 'normal', STEEL)
  doc.text(toPdfText(meta.meaning), M + 16, w.y + 47, { maxWidth: CONTENT_W - 32 })
  if (statusChanged) {
    w.font(8.5, 'normal', MUTED)
    doc.text(toPdfText(`Original draft: ${before.status}`), M + 16, w.y + 59)
  }
  w.y += boxH + 12

  // Score tiles
  const gap = 10
  const tileW = (CONTENT_W - gap * 3) / 4
  const tileH = 78
  const rl = before.reading_level
  const tiles: { label: string; value: string; sub: string[] }[] = [
    { label: 'BRAND', value: String(now.brand), sub: [`Original ${before.brand} (${signed(now.brand - before.brand)})`, SCORE_CAPTIONS.brand] },
    {
      label: 'ACCESSIBILITY',
      value: String(now.accessibility),
      sub: [`Original ${before.accessibility} (${signed(now.accessibility - before.accessibility)})`, SCORE_CAPTIONS.accessibility],
    },
    { label: 'OPEN ISSUES', value: String(now.total_issues), sub: [`of ${data.issuesFound} found`, `${data.issuesFound - now.total_issues} resolved`] },
    {
      label: 'READING LEVEL',
      value: `Grade ${data.readingNow.toFixed(1)}`,
      sub: [`Original ${rl.grade.toFixed(1)} (${signed(data.readingNow - rl.grade, 1)})`, `Target ${rl.target} for ${rl.audience}`],
    },
  ]
  w.ensure(tileH)
  tiles.forEach((t, i) => {
    const x = M + i * (tileW + gap)
    doc.setDrawColor(...RULE)
    doc.setFillColor(251, 250, 247)
    doc.setLineWidth(0.8)
    doc.roundedRect(x, w.y, tileW, tileH, 5, 5, 'FD')
    w.font(7.5, 'bold', MUTED)
    doc.text(t.label, x + 10, w.y + 16)
    w.font(t.value.length > 4 ? 15 : 20, 'bold', NAVY)
    doc.text(toPdfText(t.value), x + 10, w.y + 40)
    w.font(7.5, 'normal', MUTED)
    t.sub.forEach((s, j) => doc.text(toPdfText(s), x + 10, w.y + 55 + j * 10, { maxWidth: tileW - 16 }))
  })
  w.y += tileH + 10
  w.para(
    `Estimated time saved: about ${MANUAL_REVIEW_MINUTES} minutes of manual editorial review. Scores start at 100 and deduct 10 / 5 / 2 points per high / medium / low issue.`,
    { size: 8.5, color: MUTED },
  )

  // Improved text
  w.section('Improved text')
  const paragraphs = data.text.split('\n')
  paragraphs.forEach((p) => {
    if (!p.trim()) {
      w.y += 7
      return
    }
    w.para(p, { size: 10.5, lh: 15.5 })
  })

  // Applied changes
  w.section('Applied changes', data.appliedChanges.length)
  if (data.appliedChanges.length === 0) w.para('No changes were applied.', { color: MUTED })
  data.appliedChanges.forEach((c, i) => {
    w.ensure(60)
    w.dot(hexToRgb(c.color), M, 10)
    w.font(10, 'bold', NAVY)
    doc.text(toPdfText(`${i + 1}. ${c.ruleset}`), M + 12, w.y + 8)
    w.y += 15
    w.field('Before:', c.before ? `"${c.before}"` : '(nothing)', M + 12)
    w.field('After:', c.after ? `"${c.after}"` : '(removed)', M + 12)
    if (c.explanation) w.para(c.explanation, { x: M + 12, size: 9.5, style: 'italic', color: MUTED })
    if (c.guidelineUrl) w.link(`Guideline: ${c.guidelineTitle || c.guidelineUrl}`, c.guidelineUrl, M + 12)
    w.y += 8
  })

  // Remaining issues
  w.section('Remaining issues', data.openIssues.length)
  if (data.openIssues.length === 0) w.para('No open issues. Everything flagged has been addressed.', { color: MUTED })
  data.openIssues.forEach((iss) => {
    w.ensure(50)
    const sev = SEVERITY_META[iss.severity]
    const label = sev.label.toUpperCase()
    w.font(7.5, 'bold', hexToRgb(sev.text))
    const pillW = doc.getTextWidth(label) + 12
    doc.setFillColor(...hexToRgb(sev.bg))
    doc.roundedRect(M, w.y, pillW, 13, 6.5, 6.5, 'F')
    doc.text(label, M + 6, w.y + 9.3)
    w.font(8.5, 'normal', MUTED)
    doc.text(toPdfText(iss.ruleset + (iss.ruleName ? `  ·  ${iss.ruleName}` : '')), M + pillW + 8, w.y + 9.3)
    w.y += 18
    w.para(iss.message, { x: M + 12, size: 10, style: 'bold' })
    if (iss.excerpt) w.field('Excerpt:', `"${iss.excerpt}"`, M + 12)
    else w.field('Location:', 'Whole draft', M + 12)
    if (iss.suggestion) w.field('Suggestion:', iss.suggestion, M + 12)
    if (iss.guidelineUrl) w.link(`Guideline: ${iss.guidelineTitle || iss.guidelineUrl}`, iss.guidelineUrl, M + 12)
    w.y += 8
  })

  // Sources
  w.section('Guideline sources', data.sources.length)
  if (data.sources.length === 0) w.para('No guideline sources were referenced.', { color: MUTED })
  data.sources.forEach((s, i) => {
    w.para(`${i + 1}. ${s.title}`, { size: 9.5, style: 'bold' })
    w.link(s.url, s.url, M + 12, 8.5)
  })

  // Footer on every page
  const pages = doc.getNumberOfPages()
  for (let p = 1; p <= pages; p++) {
    doc.setPage(p)
    doc.setDrawColor(...RULE)
    doc.setLineWidth(0.6)
    doc.line(M, PAGE_H - 40, PAGE_W - M, PAGE_H - 40)
    w.font(8, 'normal', MUTED)
    doc.text(toPdfText(`UIC Brand Teammate · Compliance report · ${formatDate(data.generatedAt)}`), M, PAGE_H - 26)
    doc.text(`Page ${p} of ${pages}`, PAGE_W - M, PAGE_H - 26, { align: 'right' })
  }
  return doc
}

/**
 * Presentation metadata shared by ComplianceDisplay and the PDF report: status colors (DESIGN.md),
 * severity styling, score-group captions and the SPEC business-value numbers.
 */
import { fleschKincaidGrade } from '../../lib/readability'
import type { AnalyzeResponse, ComplianceStatus, Issue, Severity } from '../../types/api'

export interface StatusMeta {
  /** DESIGN.md status color — fills, rings, icons. */
  color: string
  /** AA-safe (≥ 4.5:1 on white and on the tint) text color. */
  text: string
  short: string
  meaning: string
}

export const STATUS_META: Record<ComplianceStatus, StatusMeta> = {
  Approved: {
    color: '#00966C',
    text: '#00684B',
    short: 'Approved',
    meaning: 'Ready to send — this draft meets UIC brand and accessibility standards.',
  },
  'Minor Revisions Needed': {
    color: '#B45309',
    text: '#9A4508',
    short: 'Minor revisions',
    meaning: 'Almost there — a few quick fixes will get this draft approved.',
  },
  'Major Revisions Needed': {
    color: '#D50032',
    text: '#B0002A',
    short: 'Major revisions',
    meaning: 'Needs work — review the high-severity issues below before publishing.',
  },
}

export interface SeverityMeta {
  label: string
  /** Pill background + text (AA-safe). */
  bg: string
  text: string
  rank: number
}

export const SEVERITY_META: Record<Severity, SeverityMeta> = {
  high: { label: 'High', bg: '#FDE7EC', text: '#A30026', rank: 0 },
  medium: { label: 'Medium', bg: '#FEF3C7', text: '#8A3C06', rank: 1 },
  low: { label: 'Low', bg: '#EEF0F3', text: '#43464D', rank: 2 },
}

export const SEVERITIES: Severity[] = ['high', 'medium', 'low']

/** Captions that explain which rulesets feed each score (lib/scoring SCORE_GROUPS). */
export const SCORE_CAPTIONS = {
  brand: 'Brand, content & tone',
  accessibility: 'Accessibility & reading level',
} as const

/** SPEC business value: manual editorial review ≈ 32 min vs ≈ 12 s with AI (used in the PDF report). */
export const MANUAL_REVIEW_MINUTES = 32

/** Color for a 0–100 score, using the status thresholds (≥ 90 / 70–89 / < 70). */
export function scoreTone(score: number): StatusMeta {
  if (score >= 90) return STATUS_META.Approved
  if (score >= 70) return STATUS_META['Minor Revisions Needed']
  return STATUS_META['Major Revisions Needed']
}

/** Hex color → rgba string. */
export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/** Document-scope issues (e.g. overall reading level) have no meaningful span to point at. */
export function isDocumentIssue(issue: Issue): boolean {
  return issue.scope === 'document' || (!issue.excerpt && issue.start === issue.end)
}

/**
 * Estimated reading grade for the current text. The backend grade for the original draft is
 * authoritative, so we shift it by the client-side Flesch–Kincaid difference between the original
 * and the current text (keeps both numbers on the same scale).
 */
export function estimateCurrentGrade(analysis: AnalyzeResponse, currentText: string): number {
  const base = analysis.scores.reading_level.grade
  if (currentText === analysis.original) return base
  const delta = fleschKincaidGrade(currentText) - fleschKincaidGrade(analysis.original)
  return Math.max(0, Math.round((base + delta) * 10) / 10)
}

export function signed(n: number, digits = 0): string {
  const v = digits ? n.toFixed(digits) : String(Math.round(n))
  return n > 0 ? `+${v}` : n < 0 ? `−${v.replace('-', '')}` : '0'
}

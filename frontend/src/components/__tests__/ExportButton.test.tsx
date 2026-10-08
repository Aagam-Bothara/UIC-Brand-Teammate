import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import logoDataUrl from '../../../public/brand/uic-logo-primary.png?inline'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RULESET_ORDER, RULESETS } from '../../config/rulesets'
import { RulesetProvider } from '../../context/RulesetContext'
import { TextProvider } from '../../context/TextContext'
import { UIProvider, useUI } from '../../context/UIContext'
import { applyChanges } from '../../lib/changes'
import { computeScores } from '../../lib/scoring'
import { SAMPLE_TEXT, mockAnalyze } from '../../services/mockData'
import type { AnalyzeResponse, RulesetId } from '../../types/api'
import ExportButton from '../ExportButton'
import { reportFilename } from '../export/clipboard'
import { buildReportData, buildReportPdf, toPdfText } from '../export/pdfReport'

function seed(revealed?: RulesetId[], text = SAMPLE_TEXT): AnalyzeResponse {
  const analysis = mockAnalyze({ text, audience: 'Students', channel: 'Email', rulesets: [...RULESET_ORDER] })
  localStorage.setItem('uic-editorial:analysis', JSON.stringify(analysis))
  localStorage.setItem('uic-editorial:text', JSON.stringify(text))
  if (revealed) localStorage.setItem('uic-editorial:revealed', JSON.stringify(revealed))
  return analysis
}

function ToastProbe() {
  const { toasts } = useUI()
  return <ul data-testid="toasts">{toasts.map((t) => <li key={t.id}>{t.message}</li>)}</ul>
}

/** Open the Export menu and pick an item. */
function choose(item: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Export' }))
  fireEvent.click(within(screen.getByRole('menu', { name: 'Export' })).getByRole('menuitem', { name: item }))
}

function renderExport() {
  return render(
    <RulesetProvider>
      <UIProvider>
        <TextProvider>
          <ExportButton />
          <ToastProbe />
        </TextProvider>
      </UIProvider>
    </RulesetProvider>,
  )
}

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
function mockClipboard(value: unknown) {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true, writable: true })
}

afterEach(() => {
  if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard)
  else delete (navigator as { clipboard?: unknown }).clipboard
  vi.restoreAllMocks()
})

describe('ExportButton', () => {
  it('is unavailable (with a reason) before an analysis exists', () => {
    const writeText = vi.fn()
    mockClipboard({ writeText })
    renderExport()
    const trigger = screen.getByRole('button', { name: 'Export' })
    expect(trigger).toHaveAttribute('aria-disabled', 'true')
    expect(trigger).toHaveAccessibleDescription('Run an analysis first to export.')
    fireEvent.click(trigger)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(writeText).not.toHaveBeenCalled()
  })

  it('copies the current text via the Clipboard API', async () => {
    const analysis = seed(['brand', 'accessibility'])
    const writeText = vi.fn().mockResolvedValue(undefined)
    mockClipboard({ writeText })
    renderExport()

    const expected = applyChanges(analysis.original, analysis.changes, (c) => c.ruleset === 'brand' || c.ruleset === 'accessibility')
    choose('Copy text')
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expected))
    expect(expected).not.toContain('<')
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
    expect(screen.getByTestId('toasts')).toHaveTextContent('Improved text copied to clipboard')
  })

  it('falls back to execCommand when the Clipboard API is unavailable', async () => {
    const analysis = seed()
    mockClipboard(undefined)
    let copied = ''
    const exec = vi.fn(() => {
      copied = document.querySelector('textarea')?.value ?? ''
      return true
    })
    Object.defineProperty(document, 'execCommand', { value: exec, configurable: true, writable: true })
    renderExport()
    choose('Copy text')
    await waitFor(() => expect(exec).toHaveBeenCalledWith('copy'))
    expect(copied).toBe(analysis.rewritten)
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('downloads a dated PDF report', async () => {
    seed()
    const createObjectURL = vi.fn((b: Blob) => (b.type === 'application/pdf' ? 'blob:pdf' : 'blob:other'))
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true, writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true, writable: true })
    const save = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      saved.push([this.download, this.href])
    })
    const saved: [string, string][] = []
    renderExport()
    fireEvent.click(screen.getByRole('button', { name: 'Export' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'PDF report' }))
    })
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(saved[0][0]).toMatch(/^uic-editorial-report-\d{4}-\d{2}-\d{2}\.pdf$/)
    expect(saved[0][1]).toBe('blob:pdf')
    expect(screen.getByTestId('toasts')).toHaveTextContent('PDF report downloaded')
  })
})

describe('buildReportPdf', () => {
  it('builds a multi-page report with the key sections', async () => {
    const longText = Array.from({ length: 14 }, () => SAMPLE_TEXT).join('\n\n')
    const analysis = mockAnalyze({ text: longText, audience: 'Students', channel: 'Email', rulesets: [...RULESET_ORDER] })
    const revealed = new Set<RulesetId>(['brand', 'accessibility', 'content'])
    const isApplied = (c: { ruleset: RulesetId }) => revealed.has(c.ruleset)
    const currentText = applyChanges(analysis.original, analysis.changes, isApplied)
    const resolved = new Set(analysis.changes.filter(isApplied).flatMap((c) => c.issue_ids))
    const openIssues = analysis.issues.filter((i) => !resolved.has(i.issue_id))
    const currentScores = { ...computeScores(openIssues), reading_level: analysis.scores.reading_level }

    const data = buildReportData({
      analysis, currentText, currentScores, openIssues, revealed, decisions: {}, rulesetById: RULESETS,
      generatedAt: new Date(2026, 9, 8),
    })
    expect(data.appliedChanges.length).toBe(analysis.changes.filter(isApplied).length)
    expect(data.openIssues.length).toBe(openIssues.length)
    expect(data.sources.length).toBeGreaterThan(0)

    const doc = await buildReportPdf(data)
    const pages = doc.getNumberOfPages()
    expect(pages).toBeGreaterThan(1)
    const out = doc.output()
    for (const s of [
      'UIC Brand Teammate - Compliance Report',
      'Audience: Students',
      'Channel: Email',
      currentScores.status,
      'Improved text',
      `Applied changes (${data.appliedChanges.length})`,
      `Remaining issues (${data.openIssues.length})`,
      'Guideline sources',
      'University of Illinois Chicago',
      `Page ${pages} of ${pages}`,
    ]) {
      expect(out).toContain(s.replace(/[()\\]/g, (c) => `\\${c}`))
    }
  })

  it('puts the official logo in the header when it loads, and still builds without it', async () => {
    const analysis = mockAnalyze({ text: SAMPLE_TEXT, audience: 'Students', channel: 'Email', rulesets: [...RULESET_ORDER] })
    const resolved = new Set(analysis.changes.flatMap((c) => c.issue_ids))
    const openIssues = analysis.issues.filter((i) => !resolved.has(i.issue_id))
    const base = buildReportData({
      analysis, currentText: analysis.rewritten, currentScores: { ...computeScores(openIssues), reading_level: analysis.scores.reading_level },
      openIssues, revealed: new Set(RULESET_ORDER), decisions: {}, rulesetById: RULESETS,
    })
    const png = logoDataUrl
    expect(png).toMatch(/^data:image\/png;base64,/)
    const withLogo = (await buildReportPdf({ ...base, logo: png })).output()
    expect(withLogo).toContain('/Subtype /Image')
    const without = (await buildReportPdf({ ...base, logo: null })).output()
    expect(without).not.toContain('/Subtype /Image')
    expect(without).toContain('UIC Brand Teammate - Compliance Report')
  })

  it('menu is keyboard operable: arrows move, Esc closes and returns focus', async () => {
    seed()
    const user = userEvent.setup()
    renderExport()
    const trigger = screen.getByRole('button', { name: 'Export' })
    trigger.focus()
    await user.keyboard('{ArrowDown}')
    const items = within(screen.getByRole('menu')).getAllByRole('menuitem')
    expect(items.map((i) => i.textContent)).toEqual(['Copy text', 'PDF report', 'Text file (.txt)'])
    expect(items[0]).toHaveFocus()
    await user.keyboard('{ArrowUp}')
    expect(items[2]).toHaveFocus()
    await user.keyboard('{Home}')
    expect(items[0]).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('maps typography outside Latin-1 so built-in fonts render it', () => {
    expect(toPdfText('A — “b” → c ≈ d… café 🎉')).toBe('A - "b" -> c ~ d... café ')
  })

  it('names the file by local date', () => {
    expect(reportFilename(new Date(2026, 0, 5))).toBe('uic-editorial-report-2026-01-05.pdf')
  })
})

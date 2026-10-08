import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RULESET_ORDER, RULESETS } from '../../config/rulesets'
import { RulesetProvider } from '../../context/RulesetContext'
import { TextProvider } from '../../context/TextContext'
import { UIProvider, useUI } from '../../context/UIContext'
import { computeScores } from '../../lib/scoring'
import { SAMPLE_TEXT, mockAnalyze } from '../../services/mockData'
import type { AnalyzeResponse, RulesetId } from '../../types/api'
import ComplianceDisplay from '../ComplianceDisplay'

function seed(revealed?: RulesetId[]): AnalyzeResponse {
  const analysis = mockAnalyze({ text: SAMPLE_TEXT, audience: 'Students', channel: 'Email', rulesets: [...RULESET_ORDER] })
  localStorage.setItem('uic-editorial:analysis', JSON.stringify(analysis))
  localStorage.setItem('uic-editorial:text', JSON.stringify(SAMPLE_TEXT))
  if (revealed) localStorage.setItem('uic-editorial:revealed', JSON.stringify(revealed))
  return analysis
}

/** Open issues when only `revealed` rulesets' changes are applied. */
function expectedOpen(analysis: AnalyzeResponse, revealed: RulesetId[]) {
  const resolved = new Set(analysis.changes.filter((c) => revealed.includes(c.ruleset)).flatMap((c) => c.issue_ids))
  return analysis.issues.filter((i) => !resolved.has(i.issue_id))
}

function SelectedProbe() {
  const { selectedChangeId } = useUI()
  return <div data-testid="selected">{selectedChangeId ?? ""}</div>
}

/** Issues live behind a collapsed "Issues (n)" disclosure (minimal UI). */
function expandIssues() {
  const toggle = screen.getByRole('button', { name: /^Issues \(\d+\)/ })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  fireEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
}

function renderDisplay() {
  return render(
    <RulesetProvider>
      <UIProvider>
        <TextProvider>
          <ComplianceDisplay />
          <SelectedProbe />
        </TextProvider>
      </UIProvider>
    </RulesetProvider>,
  )
}

describe('ComplianceDisplay', () => {
  it('shows a friendly empty state before any analysis', () => {
    renderDisplay()
    expect(screen.getByText('Your compliance score will appear here')).toBeInTheDocument()
  })

  it('shows status and before → now scores when all rulesets are revealed', () => {
    const analysis = seed()
    const now = computeScores(expectedOpen(analysis, RULESET_ORDER))
    renderDisplay()

    expect(screen.getByRole('status')).toHaveTextContent(now.status)
    const brand = screen.getByRole('img', { name: /^Brand score/ })
    expect(brand).toHaveAccessibleName(expect.stringContaining(`${now.brand} out of 100`))
    expect(brand).toHaveAccessibleName(expect.stringContaining(`from ${analysis.scores.brand} in the original draft`))
    const acc = screen.getByRole('img', { name: /^Accessibility score/ })
    expect(acc).toHaveAccessibleName(expect.stringContaining(`${now.accessibility} out of 100`))
    expect(screen.getByText(new RegExp(`Target grade ${analysis.scores.reading_level.target} for Students`))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: new RegExp(`^Issues \\(${expectedOpen(analysis, RULESET_ORDER).length}\\)`) })).toBeInTheDocument()
    // Minimal UI: no time-saved tile.
    expect(screen.queryByText(/32 min/)).not.toBeInTheDocument()
  })

  it('groups open issues by ruleset and filters by severity', () => {
    const analysis = seed([])
    renderDisplay()
    expect(screen.getByRole('status')).toHaveTextContent(analysis.scores.status)
    expandIssues()

    for (const id of RULESET_ORDER) {
      const n = analysis.issues.filter((i) => i.ruleset === id).length
      if (n === 0) continue
      const header = screen.getByRole('button', { name: new RegExp(`^${RULESETS[id].ruleset_name}\\s*${n}\\s*issues?$`) })
      expect(header).toHaveAttribute('aria-expanded', 'true')
    }
    expect(screen.getByText('Link text should describe its destination.')).toBeInTheDocument()
    expect(screen.getByText('Avoid all-caps words for emphasis.')).toBeInTheDocument()

    const filters = screen.getByRole('group', { name: 'Filter issues by severity' })
    fireEvent.click(within(filters).getByRole('button', { name: /^High/ }))
    expect(screen.getByText('Link text should describe its destination.')).toBeInTheDocument()
    expect(screen.queryByText('Avoid all-caps words for emphasis.')).not.toBeInTheDocument()
    const highCount = analysis.issues.filter((i) => i.severity === 'high').length
    expect(screen.getAllByText((_, el) => el?.tagName === 'SPAN' && el.textContent === 'High severity').length).toBe(highCount)

    // collapse a group
    const accHeader = screen.getByRole('button', { name: /^Accessibility\s*\d/ })
    fireEvent.click(accHeader)
    expect(accHeader).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Link text should describe its destination.')).not.toBeInTheDocument()
  })

  it('reflects revealed rulesets in the Resolved section', () => {
    const analysis = seed(['brand'])
    const open = expectedOpen(analysis, ['brand'])
    const resolvedCount = analysis.issues.length - open.length
    renderDisplay()

    expect(screen.getByRole('status')).toHaveTextContent(computeScores(open).status)
    expandIssues()
    const resolvedToggle = screen.getByRole('button', { name: `Resolved (${resolvedCount})` })
    expect(resolvedToggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: /^Brand\s*\d/ })).not.toBeInTheDocument()
    fireEvent.click(resolvedToggle)
    expect(screen.getByText('Use the official university name.')).toBeInTheDocument()
  })

  it('selects the matching change when an issue is clicked', () => {
    const analysis = seed([])
    renderDisplay()
    const issue = analysis.issues.find((i) => i.rule_id === 'acc-001')!
    const change = analysis.changes.find((c) => c.issue_ids.includes(issue.issue_id))!
    expandIssues()
    fireEvent.click(screen.getByRole('button', { name: /Show suggested change: Link text should describe/ }))
    expect(screen.getByTestId('selected')).toHaveTextContent(change.change_id)

    // clicking the card body works too
    const other = analysis.issues.find((i) => i.rule_id === 'brand-001')!
    const otherChange = analysis.changes.find((c) => c.issue_ids.includes(other.issue_id))!
    fireEvent.click(screen.getByText(other.message))
    expect(screen.getByTestId('selected')).toHaveTextContent(otherChange.change_id)
  })

  it('links guidelines in a new tab', () => {
    seed([])
    renderDisplay()
    expandIssues()
    const links = screen.getAllByRole('link', { name: /opens in a new tab/ })
    expect(links.length).toBeGreaterThan(0)
    for (const a of links) {
      expect(a).toHaveAttribute('target', '_blank')
      expect(a).toHaveAttribute('rel', expect.stringContaining('noopener'))
    }
  })
  it('for an issue fixed by several changes, selects the first change not applied yet', () => {
    const analysis = seed([])
    const issue = analysis.issues.find((i) => i.rule_id === 'acc-001')!
    const first = analysis.changes.find((c) => c.issue_ids.includes(issue.issue_id))!
    // Link a second (later) change to the same issue and accept the first one individually.
    const second = analysis.changes.filter((c) => c !== first).at(-1)!
    second.issue_ids = [...second.issue_ids, issue.issue_id]
    localStorage.setItem('uic-editorial:analysis', JSON.stringify(analysis))
    localStorage.setItem('uic-editorial:decisions', JSON.stringify({ [first.change_id]: 'accepted' }))
    renderDisplay()
    expandIssues()
    fireEvent.click(screen.getByRole('button', { name: /Show suggested change: Link text should describe/ }))
    expect(screen.getByTestId('selected')).toHaveTextContent(second.change_id)
  })
})

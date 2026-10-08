import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RulesetProvider, useRulesets } from '../../context/RulesetContext'
import { TextProvider, useText } from '../../context/TextContext'
import { UIProvider } from '../../context/UIContext'
import { analyze } from '../../services/api'
import type { AnalyzeResponse, ApiError } from '../../types/api'
import RulesetPanel from '../RulesetPanel'
import TextInput from '../TextInput'

// Keep tests offline and fast: analyze() runs the local mock engine instead of calling the live RAG API.
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  const { mockAnalyze } = await import('../../services/mockData')
  return { ...actual, analyze: vi.fn(async (req: Parameters<typeof actual.analyze>[0]) => mockAnalyze(req)) }
})

function Probe() {
  const { audience, channel, selectedRulesets } = useRulesets()
  const { status } = useText()
  return (
    <div data-testid="probe">
      <span data-testid="audience">{audience}</span>
      <span data-testid="channel">{channel}</span>
      <span data-testid="rulesets">{selectedRulesets.join(',')}</span>
      <span data-testid="status">{status}</span>
    </div>
  )
}

function renderPanel() {
  return render(
    <RulesetProvider>
      <UIProvider>
        <TextProvider>
          <TextInput />
          <RulesetPanel />
          <Probe />
        </TextProvider>
      </UIProvider>
    </RulesetProvider>,
  )
}

const analyzeButton = () => screen.getByRole('button', { name: /analyze/i })
const draft = () => screen.getByRole('textbox', { name: /your draft/i })
const ALL = 'brand,accessibility,content,reading_level,audience_tone'

beforeEach(() => {
  vi.mocked(analyze).mockClear()
})

describe('RulesetPanel', () => {
  it('shows audiences with their reading-level targets and persists the selection', async () => {
    const user = userEvent.setup()
    renderPanel()
    const group = screen.getByRole('radiogroup', { name: /audience/i })
    const students = within(group).getByRole('radio', { name: /students/i })
    expect(students).toBeChecked()
    // Grade targets live in the tooltip / accessible description (minimal UI).
    expect(students).toHaveAccessibleDescription(/grade 8/i)
    expect(within(group).getByRole('radio', { name: /staff/i })).toHaveAccessibleDescription(/grade 10/i)

    await user.click(within(group).getByRole('radio', { name: /faculty/i }))
    expect(within(group).getByRole('radio', { name: /faculty/i })).toBeChecked()
    expect(screen.getByTestId('audience')).toHaveTextContent('Faculty')
    expect(localStorage.getItem('uic-editorial:audience')).toBe('"Faculty"')
  })

  it('selects a channel', async () => {
    const user = userEvent.setup()
    renderPanel()
    const group = screen.getByRole('radiogroup', { name: /channel/i })
    expect(within(group).getByRole('radio', { name: /email/i })).toBeChecked()
    await user.click(within(group).getByRole('radio', { name: /social/i }))
    expect(screen.getByTestId('channel')).toHaveTextContent('Social Media')
    // Arrow keys move within the native radio group.
    await user.keyboard('{ArrowLeft}')
    expect(screen.getByTestId('channel')).toHaveTextContent('Website')
  })

  it('toggles individual rulesets', async () => {
    const user = userEvent.setup()
    renderPanel()
    expect(screen.getByTestId('rulesets')).toHaveTextContent(ALL)

    const brand = screen.getByRole('checkbox', { name: 'Brand' })
    expect(brand).toHaveAccessibleDescription(/official names/i)
    await user.click(brand)
    expect(brand).not.toBeChecked()
    expect(screen.getByTestId('rulesets')).toHaveTextContent('accessibility,content,reading_level,audience_tone')

    await user.click(brand)
    expect(screen.getByTestId('rulesets')).toHaveTextContent(ALL)
  })

  it('selects none and all, and explains why Analyze is disabled with no checks', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.type(draft(), 'Hello UIC students')
    await user.click(screen.getByRole('button', { name: /^none$/i }))
    for (const cb of screen.getAllByRole('checkbox')) expect(cb).not.toBeChecked()
    expect(analyzeButton()).toHaveAttribute('aria-disabled', 'true')
    expect(analyzeButton()).toHaveAccessibleDescription(/turn on at least one check/i)
    await user.click(analyzeButton())
    expect(analyze).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /select all/i }))
    for (const cb of screen.getAllByRole('checkbox')) expect(cb).toBeChecked()
    expect(screen.getByRole('button', { name: /select all/i })).toBeDisabled()
    expect(analyzeButton()).not.toHaveAttribute('aria-disabled')
  })

  it('gently warns about unusual combinations but still allows them', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.type(draft(), 'Hello UIC students')
    expect(screen.queryByText(/reading level is off/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Reading Level' }))
    expect(screen.getByText(/reading level is off/i)).toBeInTheDocument()
    expect(screen.getByTestId('settings-warning')).toHaveTextContent(/grade 8/i)
    // Only one warning line at a time, even when several apply.
    await user.click(screen.getByRole('checkbox', { name: 'Accessibility' }))
    expect(screen.getAllByTestId('settings-warning')).toHaveLength(1)
    expect(analyzeButton()).not.toHaveAttribute('aria-disabled')
  })

  it('disables Analyze for an empty draft with a reason', () => {
    renderPanel()
    expect(analyzeButton()).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText(/add your draft above/i)).toBeInTheDocument()
  })

  it('runs the analysis and reports completion', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.type(draft(), 'Hey guys! The University of Illinois at Chicago will host a fair. Click here.')
    await user.click(screen.getByRole('radio', { name: /faculty/i }))
    await user.click(analyzeButton())
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('success'))
    expect(analyze).toHaveBeenCalledWith(
      expect.objectContaining({ audience: 'Faculty', channel: 'Email', rulesets: ALL.split(',') }),
      expect.any(AbortSignal),
    )
    expect(screen.getByText(/analysis complete/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /analyze again/i })).toBeInTheDocument()

    // Changing a setting marks the result stale.
    await user.click(screen.getByRole('radio', { name: /staff/i }))
    expect(screen.getByRole('button', { name: /re-analyze/i })).toBeInTheDocument()
  })

  it('shows a spinner with Cancel while analyzing', async () => {
    let resolve: (r: AnalyzeResponse) => void = () => {}
    vi.mocked(analyze).mockImplementationOnce(() => new Promise<AnalyzeResponse>((r) => (resolve = r)))
    const user = userEvent.setup()
    renderPanel()
    await user.type(draft(), 'Hello UIC')
    await user.click(analyzeButton())
    expect(screen.getByRole('button', { name: /analyzing/i })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText(/checking your draft/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.getByTestId('status')).toHaveTextContent('idle')
    expect(screen.getByRole('button', { name: /analyze draft/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument()
    resolve({} as AnalyzeResponse) // late result is ignored (aborted)
  })

  it('shows errors with a Retry button that re-runs the analysis', async () => {
    const err: ApiError = { status: 503, message: 'The service is having trouble right now.', retryable: true }
    vi.mocked(analyze).mockRejectedValueOnce(err)
    const user = userEvent.setup()
    renderPanel()
    await user.type(draft(), 'Hello UIC')
    await user.click(analyzeButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/couldn’t finish the analysis/i)
    expect(alert).toHaveTextContent(err.message)

    await user.click(within(alert).getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('success'))
    expect(analyze).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

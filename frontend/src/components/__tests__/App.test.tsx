import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { mockAnalyze } from '../../services/mockData'
import type { AnalyzeRequest, AnalyzeResponse } from '../../types/api'

const api = vi.hoisted(() => ({
  ragGet: vi.fn(),
  analyze: vi.fn(),
}))

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  const { AUDIENCES, RULESET_ORDER, RULESETS } = await import('../../config/rulesets')
  return {
    ...actual,
    USE_MOCKS: true,
    rag: { get: api.ragGet },
    analyze: api.analyze,
    getRules: vi.fn(async () => RULESET_ORDER.map((id) => RULESETS[id])),
    getAudiences: vi.fn(async () => AUDIENCES),
  }
})

// The six feature components are built by other agents; stub them with minimal regions so these
// tests cover only the shell (placement, drawer, toasts, reset).
vi.mock('../TextInput', async () => {
  const { useText } = await import('../../context/TextContext')
  return {
    default: function TextInputStub() {
      const { text, setText } = useText()
      return (
        <section aria-label="Draft text">
          <textarea aria-label="Draft" value={text} onChange={(e) => setText(e.target.value)} />
        </section>
      )
    },
  }
})
vi.mock('../RulesetPanel', async () => {
  const { useText } = await import('../../context/TextContext')
  return {
    default: function RulesetPanelStub() {
      const { runAnalysis } = useText()
      return (
        <section aria-label="Ruleset settings">
          <button type="button" onClick={() => void runAnalysis()}>
            Analyze
          </button>
        </section>
      )
    },
  }
})
vi.mock('../ComparisonView', () => ({ default: () => <section aria-label="Comparison" /> }))
vi.mock('../ComplianceDisplay', () => ({ default: () => <section aria-label="Compliance" /> }))
vi.mock('../ExportButton', async () => {
  const { useUI } = await import('../../context/UIContext')
  return {
    default: function ExportStub() {
      const { notify } = useUI()
      return (
        <section aria-label="Export">
          <button type="button" onClick={() => notify('Copied to clipboard', 'success')}>
            Copy text
          </button>
        </section>
      )
    },
  }
})
vi.mock('../ChatInterface', () => ({
  default: ({ onClose }: { onClose?: () => void }) => (
    <section aria-label="Chat">
      <textarea aria-label="Message" />
      {onClose && (
        <button type="button" onClick={onClose}>
          Close chat
        </button>
      )}
    </section>
  ),
}))

function seedAnalysis() {
  const text = 'Hey guys! Come to UIC.'
  localStorage.setItem('uic-editorial:text', JSON.stringify(text))
  localStorage.setItem('uic-editorial:analysis', JSON.stringify(mockAnalyze({ text, audience: 'Students', channel: 'Email', rulesets: [] } as AnalyzeRequest, [])))
}

beforeEach(() => {
  api.ragGet.mockReset().mockResolvedValue({ data: { status: 'ok' } })
  api.analyze.mockReset().mockImplementation(async (req: AnalyzeRequest): Promise<AnalyzeResponse> => mockAnalyze(req, []))
})

afterEach(() => {
  vi.useRealTimers()
  document.body.style.overflow = ''
})

describe('App shell', () => {
  it('renders the component regions inside the providers, plus header (official logo + name) and footer', async () => {
    render(<App />)
    for (const name of ['Draft text', 'Ruleset settings', 'Comparison', 'Compliance']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument()
    }
    // Chat is mounted (inert) inside the closed drawer.
    expect(screen.getByRole('region', { name: 'Chat', hidden: true })).toBeInTheDocument()
    const banner = screen.getByRole('banner')
    expect(banner).toHaveTextContent('UIC Brand Teammate')
    for (const logo of within(banner).getAllByRole('img', { name: 'University of Illinois Chicago' })) {
      expect(logo.getAttribute('src')).toMatch(/\/brand\/uic-(logo-primary|circle-mark)\.png$/)
    }
    expect(screen.getByRole('heading', { level: 1, name: 'UIC Brand Teammate' })).toBeInTheDocument()
    // Minimal shell: no marketing hero, no step headings, no export row before an analysis.
    expect(screen.queryByText(/easy to read/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Step \d/)).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Export' })).not.toBeInTheDocument()
    expect(screen.getByRole('contentinfo')).toHaveTextContent('UIC Brand Teammate')
    expect(screen.getByRole('link', { name: /brand\.uic\.edu/ })).toHaveAttribute('href', 'https://brand.uic.edu')
    expect(screen.getByRole('link', { name: /skip to main content/i })).toHaveAttribute('href', '#main')
    await screen.findByText('Guidelines: live')
  })

  it('shows "Mock data" and "Guidelines: live" when the RAG health check is ok', async () => {
    render(<App />)
    const status = screen.getByRole('group', { name: 'Connection status' })
    expect(within(status).getByText('Mock data')).toBeInTheDocument()
    expect(await within(status).findByText('Guidelines: live')).toBeInTheDocument()
    expect(api.ragGet).toHaveBeenCalledWith('/api/rag/health', expect.anything())
  })

  it('hides the guidelines pill when the health check fails', async () => {
    api.ragGet.mockRejectedValue(new Error('Network Error'))
    render(<App />)
    await waitFor(() => expect(api.ragGet).toHaveBeenCalled())
    await act(async () => {})
    const status = screen.getByRole('group', { name: 'Connection status' })
    expect(within(status).getByText('Mock data')).toBeInTheDocument()
    expect(within(status).queryByText(/Guidelines:/)).not.toBeInTheDocument()
  })

  it('opens the chat drawer, closes it with Esc and the close button, and restores focus', async () => {
    const user = userEvent.setup()
    render(<App />)
    // Two launchers: in the header (shown from lg) and floating (below lg); jsdom shows both.
    const launchers = screen.getAllByRole('button', { name: /ask the editor/i })
    expect(launchers).toHaveLength(2)
    const launcher = launchers[1]
    expect(launcher).toHaveAttribute('aria-expanded', 'false')

    await user.click(launcher)
    const drawer = screen.getByRole('dialog', { name: 'Ask the editor' })
    expect(launcher).toHaveAttribute('aria-expanded', 'true')
    expect(drawer).not.toHaveAttribute('aria-hidden', 'true')
    expect(within(drawer).getByRole('textbox', { name: 'Message' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(launcher).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('dialog', { name: 'Ask the editor' })).not.toBeInTheDocument()
    expect(launcher).toHaveFocus()

    await user.click(launcher)
    await user.click(screen.getByRole('button', { name: 'Close chat' }))
    expect(launcher).toHaveAttribute('aria-expanded', 'false')
    expect(launcher).toHaveFocus()
  })

  it('traps Tab focus inside the open chat drawer', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(within(screen.getByRole('banner')).getByRole('button', { name: /ask the editor/i }))
    const message = screen.getByRole('textbox', { name: 'Message' })
    const close = screen.getByRole('button', { name: 'Close chat' })
    expect(message).toHaveFocus()
    await user.tab()
    expect(close).toHaveFocus()
    await user.tab()
    expect(message).toHaveFocus()
    await user.tab({ shift: true })
    expect(close).toHaveFocus()
  })

  it('shows a toast for notify() and dismisses it', async () => {
    const user = userEvent.setup()
    seedAnalysis()
    render(<App />)
    const notifications = screen.getByRole('region', { name: 'Notifications' })
    await user.click(screen.getByRole('button', { name: 'Copy text' }))
    expect(within(notifications).getByText('Copied to clipboard')).toBeInTheDocument()
    expect(within(notifications).getByRole('list')).toHaveAttribute('aria-live', 'polite')

    await user.click(within(notifications).getByRole('button', { name: 'Dismiss notification' }))
    expect(within(notifications).queryByText('Copied to clipboard')).not.toBeInTheDocument()
  })

  it('opens "How it works" with the three steps and closes it with Esc, restoring focus', async () => {
    const user = userEvent.setup()
    render(<App />)
    const trigger = within(screen.getByRole('banner')).getByRole('button', { name: 'How it works' })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'How it works' })
    for (const step of ['Paste your draft', 'Choose audience & rulesets', 'Review, toggle & export']) {
      expect(within(dialog).getByRole('heading', { name: step })).toBeInTheDocument()
    }
    expect(within(dialog).getByRole('button', { name: 'Got it' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'How it works' })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('"New draft" asks for confirmation, then clears the draft', async () => {
    const user = userEvent.setup()
    localStorage.setItem('uic-editorial:text', JSON.stringify('Hey guys! Come to UIC.'))
    render(<App />)
    const draft = screen.getByRole('textbox', { name: 'Draft' })
    expect(draft).toHaveValue('Hey guys! Come to UIC.')

    const newDraft = within(screen.getByRole('banner')).getByRole('button', { name: 'New draft' })
    await user.click(newDraft)
    const confirm = screen.getByRole('dialog', { name: 'Start a new draft?' })
    await user.click(within(confirm).getByRole('button', { name: 'Keep editing' }))
    expect(draft).toHaveValue('Hey guys! Come to UIC.')

    await user.click(newDraft)
    await user.click(screen.getByRole('button', { name: 'Clear and start over' }))
    expect(screen.queryByRole('dialog', { name: 'Start a new draft?' })).not.toBeInTheDocument()
    expect(draft).toHaveValue('')
    expect(localStorage.getItem('uic-editorial:text')).toBe('""')
    expect(screen.getByText('Ready for a new draft')).toBeInTheDocument()
  })

  it('shows a progress bar while analyzing, then focuses and scrolls to the results', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    let finish!: () => void
    api.analyze.mockImplementation(
      (req: AnalyzeRequest) => new Promise<AnalyzeResponse>((resolve) => (finish = () => resolve(mockAnalyze(req, [])))),
    )
    localStorage.setItem('uic-editorial:text', JSON.stringify('Hey guys! Come to UIC.'))
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    expect(screen.getByRole('progressbar', { name: /analyzing your draft/i })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Results' })).toHaveAttribute('aria-busy', 'true')

    await act(async () => finish())
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument())
    const resultsHeading = screen.getByRole('heading', { name: 'Results' })
    expect(resultsHeading).toHaveFocus()
    expect(scrollIntoView).toHaveBeenCalled()
    expect(screen.getByRole('region', { name: 'Export' })).toBeInTheDocument()
    delete (Element.prototype as Partial<Element>).scrollIntoView
  })

  it('does not scroll to the results when their heading is already comfortably in view', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ top: 200, bottom: 224 } as DOMRect)
    localStorage.setItem('uic-editorial:text', JSON.stringify('Hey guys! Come to UIC.'))
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Results' })).toHaveFocus())
    expect(scrollIntoView).not.toHaveBeenCalled()
    rect.mockRestore()
    delete (Element.prototype as Partial<Element>).scrollIntoView
  })

  it('still closes the chat with Esc, and pulls Tab back in, after focus escaped to a toast', async () => {
    const user = userEvent.setup()
    seedAnalysis()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Copy text' }))
    const launcher = within(screen.getByRole('banner')).getByRole('button', { name: /ask the editor/i })
    await user.click(launcher)
    // Clicking the toast's dismiss button moves focus outside the drawer.
    const notifications = screen.getByRole('region', { name: 'Notifications' })
    within(notifications).getByRole('button', { name: 'Dismiss notification' }).focus()
    await user.tab()
    expect(screen.getByRole('textbox', { name: 'Message' })).toHaveFocus()
    within(notifications).getByRole('button', { name: 'Dismiss notification' }).focus()
    await user.keyboard('{Escape}')
    expect(launcher).toHaveAttribute('aria-expanded', 'false')
    expect(document.body.style.overflow).toBe('')
  })

  it('hides the floating chat launcher while scrolling down and shows it again on scroll up', async () => {
    render(<App />)
    const fab = screen.getAllByRole('button', { name: /ask the editor/i })[1]
    const scrollTo = async (y: number) => {
      Object.defineProperty(window, 'scrollY', { value: y, configurable: true })
      await act(async () => {
        window.dispatchEvent(new Event('scroll'))
        await new Promise((r) => requestAnimationFrame(() => r(null)))
      })
    }
    Object.defineProperty(document.documentElement, 'scrollHeight', { value: 5000, configurable: true })
    await scrollTo(400)
    expect(fab.className).toMatch(/opacity-0/)
    await scrollTo(300)
    expect(fab.className).not.toMatch(/opacity-0/)
    await scrollTo(0)
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
  })
})

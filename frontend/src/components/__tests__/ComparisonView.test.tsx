import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { RULESET_ORDER } from '../../config/rulesets'
import { RulesetProvider } from '../../context/RulesetContext'
import { TextProvider, useText } from '../../context/TextContext'
import { UIProvider } from '../../context/UIContext'
import { SAMPLE_TEXT, mockAnalyze } from '../../services/mockData'
import type { AnalyzeResponse, RulesetId } from '../../types/api'
import ComparisonView from '../ComparisonView'
import { snippet } from '../comparison/utils'
import { useUI } from '../../context/UIContext'

// Never hit the network: analysis stays pending so the loading state can be observed.
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  return { ...actual, analyze: vi.fn(() => new Promise(() => {})) }
})

function seed({ text = SAMPLE_TEXT, draft, rulesets = [...RULESET_ORDER] }: { text?: string; draft?: string; rulesets?: RulesetId[] } = {}) {
  const analysis = mockAnalyze({ text, audience: 'Students', channel: 'Email', rulesets })
  localStorage.setItem('uic-editorial:analysis', JSON.stringify(analysis))
  localStorage.setItem('uic-editorial:text', JSON.stringify(draft ?? text))
  localStorage.setItem('uic-editorial:rulesets', JSON.stringify(rulesets))
  return analysis
}

function AnalyzeButton() {
  const { runAnalysis } = useText()
  return (
    <button type="button" onClick={() => void runAnalysis()}>
      Test analyze
    </button>
  )
}

async function renderView(extra?: ReactNode) {
  const utils = render(
    <RulesetProvider>
      <UIProvider>
        <TextProvider>
          {extra}
          <ComparisonView />
        </TextProvider>
      </UIProvider>
    </RulesetProvider>,
  )
  await act(async () => {}) // flush RulesetProvider's async metadata load
  return utils
}

const improved = () => screen.getByRole('region', { name: 'Improved text' })
const original = () => screen.getByRole('region', { name: 'Original text' })
const chip = (name: string) => screen.getByRole('button', { name: new RegExp(`^${name}, \\d+ change`) })
const struck = () => Array.from(original().querySelectorAll('del')).map((d) => d.textContent)

describe('ComparisonView', () => {
  it('shows a friendly empty state before analysis', async () => {
    await renderView()
    expect(screen.getByText('Paste your draft and click Analyze')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try a sample announcement/i })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Improved text' })).not.toBeInTheDocument()
  })

  it('shows the draft with a shimmer while analyzing', async () => {
    localStorage.setItem('uic-editorial:text', JSON.stringify('Hey guys, click here to register.'))
    const user = userEvent.setup()
    await renderView(<AnalyzeButton />)
    await user.click(screen.getByRole('button', { name: 'Test analyze' }))
    expect(screen.getByText(/checking your draft against uic guidelines/i)).toBeInTheDocument()
    expect(original()).toHaveTextContent('Hey guys, click here to register.')
    expect(improved()).toHaveAttribute('aria-busy', 'true')
  })

  it('renders side-by-side panes with all changes applied and a summary line', async () => {
    const analysis = seed()
    await renderView()
    expect(improved().textContent).toBe(analysis.rewritten)
    expect(original().textContent).toBe(analysis.original)
    const n = analysis.changes.length
    expect(screen.getByText(/changes applied/).textContent).toBe(`${n} of ${n} changes applied`)
    expect(screen.getByText(`${RULESET_ORDER.length} of ${RULESET_ORDER.length} rulesets applied`)).toBeInTheDocument()
    expect(screen.queryByText(/your draft changed/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reset decisions/i })).not.toBeInTheDocument()
  })

  it('toggling a ruleset removes and restores its rewritten text (and strikethrough)', async () => {
    seed()
    const user = userEvent.setup()
    await renderView()
    expect(improved()).toHaveTextContent('University of Illinois Chicago')
    expect(struck()).toContain('University of Illinois at Chicago')

    const brand = chip('Brand')
    expect(brand).toHaveAttribute('aria-pressed', 'true')
    await user.click(brand)
    expect(brand).toHaveAttribute('aria-pressed', 'false')
    expect(improved()).toHaveTextContent('University of Illinois at Chicago')
    expect(struck()).not.toContain('University of Illinois at Chicago')
    // Other rulesets are unaffected.
    expect(improved()).toHaveTextContent('Hello, everyone')
    expect(document.querySelector('[aria-live="polite"]')?.textContent).toMatch(/Brand changes hidden/)

    await user.click(brand)
    expect(improved()).toHaveTextContent('University of Illinois Chicago')
    expect(improved()).not.toHaveTextContent('University of Illinois at Chicago')
  })

  it('reveals rulesets one at a time in SPEC order', async () => {
    const analysis = seed()
    const user = userEvent.setup()
    await renderView()
    await user.click(screen.getByRole('button', { name: /original only/i }))
    expect(improved().textContent).toBe(analysis.original)
    expect(screen.getByText(`0 of 5 rulesets applied`)).toBeInTheDocument()

    const names = ['Brand', 'Accessibility', 'Content', 'Reading Level', 'Audience Tone']
    for (const [i, name] of names.entries()) {
      await user.click(screen.getByRole('button', { name: `Reveal next: ${name}` }))
      expect(chip(name)).toHaveAttribute('aria-pressed', 'true')
      for (const later of names.slice(i + 1)) expect(chip(later)).toHaveAttribute('aria-pressed', 'false')
      expect(screen.getByText(`${i + 1} of 5 rulesets applied`)).toBeInTheDocument()
    }
    expect(improved().textContent).toBe(analysis.rewritten)
    expect(screen.queryByRole('button', { name: /reveal next/i })).not.toBeInTheDocument()

    // Once everything is shown, the same primary button replays the demo from the original.
    await user.click(screen.getByRole('button', { name: /replay step by step/i }))
    expect(improved().textContent).toBe(analysis.original)
    expect(screen.getByRole('button', { name: 'Reveal next: Brand' })).toBeInTheDocument()
  })

  it('opens an explanation popover and closes it on Esc, returning focus to the change', async () => {
    seed()
    const user = userEvent.setup()
    await renderView()
    const mark = screen.getByRole('button', { name: /“University of Illinois Chicago”: Brand change/ })
    await user.click(mark)

    const dialog = screen.getByRole('dialog', { name: /Brand change/ })
    expect(dialog).toHaveTextContent('The official name is “University of Illinois Chicago”')
    expect(within(dialog).getByText('High')).toBeInTheDocument()
    const link = within(dialog).getByRole('link', { name: /Name and boilerplate/ })
    expect(link).toHaveAttribute('href', 'https://brand.uic.edu/messaging/name-and-boilerplate/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(mark).toHaveAttribute('aria-expanded', 'true')

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mark).toHaveFocus()
  })

  it('is keyboard operable: Enter on a change opens it', async () => {
    seed()
    const user = userEvent.setup()
    await renderView()
    const mark = screen.getByRole('button', { name: /“Hello, everyone”: Audience Tone change/ })
    mark.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('dialog', { name: /Audience Tone change/ })).toBeInTheDocument()
  })

  it('individual accept/reject overrides the ruleset toggle (FR-10)', async () => {
    const analysis = seed()
    const total = analysis.changes.length
    const user = userEvent.setup()
    await renderView()

    // Reject one tone change while its ruleset is on: original wording comes back.
    await user.click(screen.getByRole('button', { name: /“Hello, everyone”: Audience Tone change/ }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reject' }))
    expect(improved()).toHaveTextContent('Hey guys')
    const rejected = screen.getByRole('button', { name: /“Hey guys”: Audience Tone change, rejected/ })
    expect(rejected.style.border).toContain('dashed')
    expect(screen.getByText(/changes applied/).textContent).toMatch(new RegExp(`^${total - 1} of ${total} changes applied · 1 reviewed by you`))
    await user.keyboard('{Escape}')

    // Hide Brand, then accept the brand change from the changes list: it stays applied.
    await user.click(chip('Brand'))
    expect(improved()).toHaveTextContent('University of Illinois at Chicago')
    const list = screen.getByRole('complementary', { name: 'All changes' })
    // The list is collapsed by default (minimal UI).
    const listToggle = within(list).getByRole('button', { name: /All changes/ })
    expect(listToggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(listToggle)
    await user.click(within(list).getByRole('button', { name: /University of Illinois at Chicago/ }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Accept' }))
    expect(improved()).toHaveTextContent('University of Illinois Chicago')
    expect(screen.getByRole('button', { name: /“University of Illinois Chicago”: Brand change, accepted/ })).toBeInTheDocument()

    // Toggling rulesets doesn't override decisions.
    await user.click(chip('Audience Tone'))
    await user.click(chip('Audience Tone'))
    expect(improved()).toHaveTextContent('Hey guys')

    // Reset decisions restores ruleset-level behaviour.
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: /reset decisions/i }))
    expect(improved()).toHaveTextContent('Hello, everyone')
    expect(improved()).toHaveTextContent('University of Illinois at Chicago')
    expect(screen.queryByRole('button', { name: /reset decisions/i })).not.toBeInTheDocument()
  })

  it('reset to ruleset clears an individual decision', async () => {
    seed()
    const user = userEvent.setup()
    await renderView()
    await user.click(screen.getByRole('button', { name: /“Hello, everyone”: Audience Tone change/ }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Reject' }))
    expect(within(dialog).getByRole('button', { name: 'Rejected' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(within(dialog).getByRole('button', { name: /reset to ruleset/i }))
    expect(improved()).toHaveTextContent('Hello, everyone')
  })

  it('highlights toggle shows clean text when off', async () => {
    const analysis = seed()
    const user = userEvent.setup()
    await renderView()
    expect(within(improved()).getAllByRole('button').length).toBe(analysis.changes.length)
    expect(struck().length).toBeGreaterThan(0)

    const toggle = screen.getByRole('button', { name: /highlights/i })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(within(improved()).queryAllByRole('button')).toHaveLength(0)
    expect(struck()).toHaveLength(0)
    expect(improved().textContent).toBe(analysis.rewritten)
    expect(original().textContent).toBe(analysis.original)
  })

  it('shows a stale banner when the draft changed since analysis', async () => {
    seed({ draft: `${SAMPLE_TEXT} Updated.` })
    await renderView()
    expect(screen.getByText(/draft or settings changed — re-run analyze/i)).toBeInTheDocument()
  })

  it('disables rulesets that produced no changes', async () => {
    seed({ text: 'Hey guys, click here to register.' })
    await renderView()
    const brand = screen.getByRole('button', { name: /Brand.*No changes/ })
    expect(brand).toBeDisabled()
    expect(chip('Audience Tone')).toBeEnabled()
  })

  it('handles ~5,000-word drafts', async () => {
    const big = Array.from({ length: 70 }, () => SAMPLE_TEXT).join('\n\n')
    const analysis: AnalyzeResponse = seed({ text: big })
    expect(analysis.changes.length).toBeGreaterThan(500)
    const user = userEvent.setup()
    await renderView()
    expect(improved().textContent).toBe(analysis.rewritten)
    await user.click(chip('Content'))
    expect(improved().textContent).not.toBe(analysis.rewritten)
  })
  it('returns focus to an outside opener (e.g. the issues list) when Esc closes the popover', async () => {
    const analysis = seed()
    const id = analysis.changes[0].change_id
    function Opener() {
      const { selectChange } = useUI()
      return (
        <button type="button" onClick={() => selectChange(id)}>
          Show suggested change
        </button>
      )
    }
    const user = userEvent.setup()
    await renderView(<Opener />)
    const opener = screen.getByRole('button', { name: 'Show suggested change' })
    await user.click(opener)
    expect(screen.getByRole('dialog')).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('pins the popover to the pane edge when its change is scrolled out of the pane, and caps its height', async () => {
    seed()
    const rect = (top: number, bottom: number, left = 0, width = 800) =>
      ({ top, bottom, left, right: left + width, width, height: bottom - top, x: left, y: top, toJSON: () => ({}) }) as DOMRect
    const bcr = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (this.hasAttribute('data-pane-scroll')) return rect(150, 650)
      if (this.querySelector(':scope > [role="group"], :scope > div > [data-pane-scroll]')) return rect(100, 700)
      return rect(0, 0)
    })
    let anchorTop = -500
    const gcr = vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(function (this: HTMLElement) {
      return (this.dataset.anchor ? [rect(anchorTop, anchorTop + 20, 300, 80)] : []) as unknown as DOMRectList
    })
    Object.defineProperty(window, 'innerHeight', { value: 1000, configurable: true })
    const user = userEvent.setup()
    await renderView()
    await user.click(screen.getByRole('button', { name: /“Hello, everyone”: Audience Tone change/ }))
    const dialog = screen.getByRole('dialog')
    // Anchor far above the pane → reference clamps to the pane top (150): 150 - 100 + 8.
    await act(async () => window.dispatchEvent(new Event('resize')))
    await act(async () => new Promise<void>((r) => requestAnimationFrame(() => r())))
    expect(dialog.style.getPropertyValue('--pop-top')).toBe('58px')

    // A tall popover with no room on either side gets the roomier side and a max height.
    Object.defineProperty(dialog, 'scrollHeight', { value: 900, configurable: true })
    anchorTop = 480
    await act(async () => window.dispatchEvent(new Event('resize')))
    await act(async () => new Promise<void>((r) => requestAnimationFrame(() => r())))
    // below: 1000 - 500 - 16 = 484; above: 480 - 16 = 464 → below, capped at 484.
    expect(dialog.style.getPropertyValue('--pop-max-h')).toBe('484px')
    bcr.mockRestore()
    gcr.mockRestore()
  })

  it('names whitespace-only and emoji edits visibly in summaries', () => {
    expect(snippet('  ')).toBe('(space)')
    expect(snippet('\n\n')).toBe('(line break)')
    expect(snippet('')).toBe('')
    expect(snippet('ab🎉cd', 4)).toBe('ab🎉…')
  })
})

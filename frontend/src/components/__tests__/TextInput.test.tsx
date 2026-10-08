import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RulesetProvider } from '../../context/RulesetContext'
import { TextProvider, useText } from '../../context/TextContext'
import { UIProvider } from '../../context/UIContext'
import { analyze } from '../../services/api'
import { DEMO_SAMPLES } from '../../data/demoSamples'
import RulesetPanel from '../RulesetPanel'
import TextInput from '../TextInput'

// Keep tests offline and fast: analyze() runs the local mock engine instead of calling the live RAG API.
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  const { mockAnalyze } = await import('../../services/mockData')
  return { ...actual, analyze: vi.fn(async (req: Parameters<typeof actual.analyze>[0]) => mockAnalyze(req)) }
})

function StatusProbe() {
  const { status } = useText()
  return <span data-testid="status">{status}</span>
}

function renderInput() {
  return render(
    <RulesetProvider>
      <UIProvider>
        <TextProvider>
          <TextInput />
          <RulesetPanel />
          <StatusProbe />
        </TextProvider>
      </UIProvider>
    </RulesetProvider>,
  )
}

const draft = () => screen.getByRole('textbox', { name: /your draft/i }) as HTMLTextAreaElement
const analyzeButton = () => screen.getByRole('button', { name: /analyze/i })

beforeEach(() => {
  vi.mocked(analyze).mockClear()
})

describe('TextInput', () => {
  it('renders an accessible, labelled writing surface with the shortcut hint', () => {
    renderInput()
    expect(draft()).toHaveAttribute('rows', '10')
    expect(draft()).toHaveAttribute('aria-keyshortcuts', expect.stringContaining('Enter'))
    expect(screen.getByText(/^to analyze$/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /clear/i })).toBeDisabled()
  })

  it('updates word and character counts as the user types', async () => {
    const user = userEvent.setup()
    renderInput()
    await user.type(draft(), 'Hello UIC world')
    expect(screen.getByTestId('draft-counts')).toHaveTextContent('3 / 5,000 words')
    expect(screen.getByTestId('draft-counts')).toHaveAttribute('title', '15 characters')
    expect(screen.getByRole('meter', { name: /word limit/i })).toHaveAttribute('aria-valuetext', '3 of 5,000 words')
  })

  it('loads a demo sample from the menu and applies its audience and channel', async () => {
    const user = userEvent.setup()
    renderInput()
    await user.click(screen.getByRole('button', { name: /try a sample/i }))
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(DEMO_SAMPLES.length)
    const sample = DEMO_SAMPLES.find((s) => s.audience !== 'Students' && s.channel !== 'Email')!
    await user.click(screen.getByRole('menuitem', { name: new RegExp(sample.title.slice(0, 20).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }))
    expect(draft().value).toBe(sample.text)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('uic-editorial:audience')!)).toBe(sample.audience)
    expect(JSON.parse(localStorage.getItem('uic-editorial:channel')!)).toBe(sample.channel)
    expect(screen.getByTestId('draft-counts')).not.toHaveTextContent(/^0 \//)
  })

  it('sample menu: featured first, Esc closes and refocuses the button', async () => {
    const user = userEvent.setup()
    renderInput()
    const btn = screen.getByRole('button', { name: /try a sample/i })
    await user.click(btn)
    expect(screen.getAllByRole('menuitem')[0]).toHaveTextContent(DEMO_SAMPLES.find((s) => s.featured)!.title)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(btn).toHaveFocus()
  })

  it('clears the draft and offers undo', async () => {
    const user = userEvent.setup()
    renderInput()
    await user.type(draft(), 'Keep this please')
    await user.click(screen.getByRole('button', { name: /clear/i }))
    expect(draft().value).toBe('')
    await user.click(screen.getByRole('button', { name: /undo/i }))
    expect(draft().value).toBe('Keep this please')
    expect(screen.queryByRole('button', { name: /undo/i })).not.toBeInTheDocument()
  })

  it('pastes from the clipboard when the Clipboard API is available', async () => {
    const user = userEvent.setup() // installs a clipboard stub on navigator
    await navigator.clipboard.writeText('Pasted announcement')
    renderInput()
    await user.click(screen.getByRole('button', { name: /^paste$/i }))
    await waitFor(() => expect(draft().value).toBe('Pasted announcement'))
  })

  it('shows a helpful message and blocks analysis when over the 5,000-word limit', () => {
    renderInput()
    fireEvent.change(draft(), { target: { value: 'word '.repeat(5002) } })
    expect(screen.getByRole('alert')).toHaveTextContent('2 words over the 5,000-word limit')
    expect(draft()).toHaveAttribute('aria-invalid', 'true')
    expect(analyzeButton()).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText(/over the 5,000-word limit\. Shorten it/i)).toBeInTheDocument()
  })

  it('warns in amber when approaching the limit', () => {
    renderInput()
    fireEvent.change(draft(), { target: { value: 'word '.repeat(4500) } })
    expect(screen.getByRole('status')).toHaveTextContent(/getting close/i)
    expect(analyzeButton()).not.toHaveAttribute('aria-disabled')
  })

  it('runs the analysis with Cmd+Enter and Ctrl+Enter', async () => {
    const user = userEvent.setup()
    renderInput()
    await user.type(draft(), 'The University of Illinois at Chicago is great.')
    await user.keyboard('{Meta>}{Enter}{/Meta}')
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('success'))
    expect(analyze).toHaveBeenCalledTimes(1)
    expect(draft().value).not.toContain('\n') // the shortcut doesn't insert a newline

    await user.keyboard('{Control>}{Enter}{/Control}')
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2))
  })

  it('does not analyze an empty draft from the shortcut', async () => {
    const user = userEvent.setup()
    renderInput()
    await user.click(draft())
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(analyze).not.toHaveBeenCalled()
    expect(screen.getByTestId('status')).toHaveTextContent('idle')
  })

  it('shows "Edited since last analysis" after the draft changes', async () => {
    const user = userEvent.setup()
    renderInput()
    await user.type(draft(), 'Hey guys, register ASAP.')
    await user.keyboard('{Control>}{Enter}{/Control}')
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('success'))
    expect(screen.queryByText(/edited since last analysis/i)).not.toBeInTheDocument()
    await user.type(draft(), ' Thanks!')
    expect(screen.getByText(/edited since last analysis/i)).toBeInTheDocument()
  })
})

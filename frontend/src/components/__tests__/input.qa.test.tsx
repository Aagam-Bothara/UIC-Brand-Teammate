/** QA regression tests for TextInput / RulesetPanel / input/* edge cases. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RulesetProvider } from '../../context/RulesetContext'
import { TextProvider, useText } from '../../context/TextContext'
import { UIProvider } from '../../context/UIContext'
import { analyze } from '../../services/api'
import RulesetPanel from '../RulesetPanel'
import TextInput from '../TextInput'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  const { mockAnalyze } = await import('../../services/mockData')
  return { ...actual, analyze: vi.fn(async (req: Parameters<typeof actual.analyze>[0]) => mockAnalyze(req)) }
})

function TextProbe() {
  const { text } = useText()
  return <output data-testid="text">{JSON.stringify(text)}</output>
}

const renderAll = () =>
  render(
    <RulesetProvider>
      <UIProvider>
        <TextProvider>
          <TextInput />
          <RulesetPanel />
          <TextProbe />
        </TextProvider>
      </UIProvider>
    </RulesetProvider>,
  )

const draft = () => screen.getByRole('textbox', { name: /your draft/i }) as HTMLTextAreaElement
const analyzeButton = () => screen.getByRole('button', { name: /analyze/i })

beforeEach(() => {
  vi.mocked(analyze).mockClear()
})

describe('TextInput edge cases', () => {
  it('does not analyze on Cmd+Enter while an IME composition is in progress', () => {
    renderAll()
    fireEvent.change(draft(), { target: { value: 'にほんご' } })
    fireEvent.keyDown(draft(), { key: 'Enter', metaKey: true, isComposing: true })
    fireEvent.keyDown(draft(), { key: 'Enter', ctrlKey: true, keyCode: 229 })
    expect(analyze).not.toHaveBeenCalled()
    fireEvent.keyDown(draft(), { key: 'Enter', metaKey: true })
    expect(analyze).toHaveBeenCalledTimes(1)
  })

  it('normalizes Windows line endings when pasting (so the draft is not instantly "edited")', async () => {
    const user = userEvent.setup()
    await navigator.clipboard.writeText('Line one\r\nLine two\rLine three')
    renderAll()
    await user.click(screen.getByRole('button', { name: /^paste$/i }))
    await waitFor(() => expect(screen.getByTestId('text')).toHaveTextContent('"Line one\\nLine two\\nLine three"'))
  })

  it('reports a clipboard read failure without changing the draft', async () => {
    const user = userEvent.setup()
    renderAll()
    vi.spyOn(navigator.clipboard, 'readText').mockRejectedValueOnce(new Error('denied'))
    fireEvent.change(draft(), { target: { value: 'Keep me' } })
    await user.click(screen.getByRole('button', { name: /^paste$/i }))
    expect(draft().value).toBe('Keep me')
  })

  it('allows exactly 5,000 words and exactly 40,000 characters, blocks one more', () => {
    renderAll()
    fireEvent.change(draft(), { target: { value: 'word '.repeat(5000).trim() } })
    expect(analyzeButton()).not.toHaveAttribute('aria-disabled')
    fireEvent.change(draft(), { target: { value: 'word '.repeat(5001).trim() } })
    expect(analyzeButton()).toHaveAttribute('aria-disabled', 'true')
    fireEvent.change(draft(), { target: { value: 'x'.repeat(40000) } })
    expect(analyzeButton()).not.toHaveAttribute('aria-disabled')
    fireEvent.change(draft(), { target: { value: 'x'.repeat(40001) } })
    expect(analyzeButton()).toHaveAttribute('aria-disabled', 'true')
    expect(analyzeButton()).toHaveAccessibleDescription(/40,000-character limit/)
  })
})

describe('RulesetPanel a11y', () => {
  it('every segmented option (including "Social Media") has a working accessible description', () => {
    renderAll()
    const channel = screen.getByRole('radiogroup', { name: /channel/i })
    expect(within(channel).getByRole('radio', { name: /social/i })).toHaveAccessibleDescription(/short posts/i)
    const audience = screen.getByRole('radiogroup', { name: /audience/i })
    expect(within(audience).getByRole('radio', { name: /students/i })).toHaveAccessibleDescription(/grade 8/i)
  })
})

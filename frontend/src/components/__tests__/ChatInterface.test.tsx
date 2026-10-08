import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AUDIENCES, RULESET_ORDER, RULESETS } from '../../config/rulesets'
import { RulesetProvider } from '../../context/RulesetContext'
import { TextProvider } from '../../context/TextContext'
import { UIProvider } from '../../context/UIContext'
import { analyze, refine } from '../../services/api'
import { useText } from '../../context/TextContext'
import { mockAnalyze, SAMPLE_TEXT } from '../../services/mockData'
import type { RefineResponse } from '../../types/api'
import ChatInterface from '../ChatInterface'
import { STYLE_SUGGESTIONS } from '../chat/chatHelpers'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  return {
    ...actual,
    refine: vi.fn(),
    analyze: vi.fn(),
    getRules: vi.fn(async () => RULESET_ORDER.map((id) => RULESETS[id])),
    getAudiences: vi.fn(async () => AUDIENCES),
  }
})

const refineMock = vi.mocked(refine)

const RICH_REPLY = [
  'Use the **official name** on first reference.',
  '',
  '- University of Illinois Chicago',
  '- UIC on second reference',
  '',
  'From the UIC Name and boilerplate (University name):',
  '> Never use “at” between Illinois and Chicago.',
  '',
  'Read more at https://brand.uic.edu/messaging/name-and-boilerplate/.',
].join('\n')

function renderChat() {
  const user = userEvent.setup()
  const utils = render(
    <div style={{ height: 600 }}>
      <RulesetProvider>
        <UIProvider>
          <TextProvider>
            <ChatInterface />
          </TextProvider>
        </UIProvider>
      </RulesetProvider>
    </div>,
  )
  const composer = () => screen.getByRole('textbox', { name: /message the editor/i })
  const sendButton = () => screen.getByRole('button', { name: /send message/i })
  return { user, composer, sendButton, ...utils }
}

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  refineMock.mockReset()
  refineMock.mockResolvedValue({ reply: RICH_REPLY })
})

describe('ChatInterface', () => {
  it('shows a friendly empty state with style suggestions before an analysis', () => {
    const { composer, sendButton } = renderChat()
    expect(screen.getByRole('heading', { name: 'Ask the editor' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /how can i help/i })).toBeInTheDocument()
    // At most three starter prompts.
    for (const s of STYLE_SUGGESTIONS.slice(0, 3)) expect(screen.getByRole('button', { name: s })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: STYLE_SUGGESTIONS[3] })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ask the editor' })).toHaveAccessibleDescription(/General style help · Students · Email/)
    expect(composer()).toHaveValue('')
    expect(sendButton()).toBeDisabled()
    // No clear button while the conversation is empty.
    expect(screen.queryByRole('button', { name: /clear conversation/i })).not.toBeInTheDocument()
  })

  it('adapts suggestions once a draft has been analyzed', () => {
    const analysis = mockAnalyze({ text: SAMPLE_TEXT, audience: 'Students', channel: 'Email', rulesets: [...RULESET_ORDER] })
    localStorage.setItem('uic-editorial:text', JSON.stringify(SAMPLE_TEXT))
    localStorage.setItem('uic-editorial:analysis', JSON.stringify(analysis))
    renderChat()
    expect(screen.getByRole('heading', { name: 'Ask the editor' })).toHaveAccessibleDescription(/Using your checked draft/)
    // Students + Email: explain a real change, an audience-specific tone request, a channel-specific action.
    for (const s of ['Why did you change the university name?', 'Make it warmer and more energetic for students', 'Suggest a clear subject line for this email']) {
      expect(screen.getByRole('button', { name: s })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: STYLE_SUGGESTIONS[0] })).not.toBeInTheDocument()
  })

  it('tailors starter prompts to the selected audience and channel', () => {
    localStorage.setItem('uic-editorial:audience', JSON.stringify('Faculty'))
    localStorage.setItem('uic-editorial:channel', JSON.stringify('Social Media'))
    renderChat()
    expect(screen.getByRole('button', { name: 'What tone works best for faculty?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'What should a UIC social media post always include?' })).toBeInTheDocument()
  })

  it('sends a suggested prompt when its chip is clicked', async () => {
    const { user, composer } = renderChat()
    await user.click(screen.getByRole('button', { name: 'What should a UIC email always include?' }))

    expect(refineMock).toHaveBeenCalledTimes(1)
    expect(refineMock.mock.calls[0][0]).toMatchObject({ message: 'What should a UIC email always include?', audience: 'Students', channel: 'Email' })
    const messages = await screen.findByRole('list', { name: 'Messages' })
    expect(within(messages).getByText('What should a UIC email always include?')).toBeInTheDocument()
    expect(await within(messages).findByText('official name')).toBeInTheDocument()
    expect(composer()).toHaveFocus()
  })

  it('sends on Enter but inserts a newline on Shift+Enter', async () => {
    const { user, composer, sendButton } = renderChat()
    await user.click(composer())
    await user.keyboard('Hello{Shift>}{Enter}{/Shift}world')
    expect(refineMock).not.toHaveBeenCalled()
    expect(composer()).toHaveValue('Hello\nworld')
    expect(sendButton()).toBeEnabled()

    await user.keyboard('{Enter}')
    expect(refineMock).toHaveBeenCalledTimes(1)
    expect(refineMock.mock.calls[0][0].message).toBe('Hello\nworld')
    expect(composer()).toHaveValue('')
  })

  it('does not send whitespace-only messages', async () => {
    const { user, composer, sendButton } = renderChat()
    await user.type(composer(), '   {Enter}')
    expect(refineMock).not.toHaveBeenCalled()
    expect(sendButton()).toBeDisabled()
  })

  it('shows a typing indicator while a reply is pending and announces the reply', async () => {
    const pending = deferred<RefineResponse>()
    refineMock.mockReturnValueOnce(pending.promise)
    const { user, composer, sendButton } = renderChat()

    await user.type(composer(), 'What tone should I use?')
    await user.click(sendButton())

    expect(await screen.findByText('The editor is typing a reply…')).toBeInTheDocument()
    await user.type(composer(), 'next question')
    expect(sendButton()).toBeDisabled()
    // Enter while pending doesn't send a second message.
    await user.keyboard('{Enter}')
    expect(refineMock).toHaveBeenCalledTimes(1)

    pending.resolve({ reply: 'Be **warm** and direct.' })
    expect(await screen.findByText(/Editor replied: Be warm and direct\./)).toBeInTheDocument()
    expect(screen.queryByText('The editor is typing a reply…')).not.toBeInTheDocument()
    expect(sendButton()).toBeEnabled()
  })

  it('renders assistant markdown: bold, lists, guideline quotes and safe external links', async () => {
    const { user, composer } = renderChat()
    await user.type(composer(), 'How do I write the name?{Enter}')
    const messages = await screen.findByRole('list', { name: 'Messages' })
    await within(messages).findByText('official name')

    expect(within(messages).getByText('official name').tagName).toBe('STRONG')
    expect(within(messages).getByText('University of Illinois Chicago').tagName).toBe('LI')
    expect(within(messages).getByText('UIC on second reference').tagName).toBe('LI')

    const quote = within(messages).getByText(/Never use “at” between Illinois and Chicago\./)
    expect(quote.closest('blockquote')).not.toBeNull()
    expect(quote.closest('figure')).toHaveTextContent('UIC guideline')

    const link = within(messages).getByRole('link', { name: /brand\.uic\.edu\/messaging\/name-and-boilerplate/ })
    expect(link).toHaveAttribute('href', 'https://brand.uic.edu/messaging/name-and-boilerplate/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    // Trailing sentence punctuation stays outside the link.
    expect(link.textContent).not.toMatch(/\.\s*\(opens/)
  })

  it('cites named UIC guideline pages as source links', async () => {
    refineMock.mockResolvedValueOnce({ reply: 'From the UIC Voice and tone guide: be **confident** and plain-spoken.' })
    const { user, composer } = renderChat()
    await user.type(composer(), 'Tone?{Enter}')
    const source = await screen.findByRole('link', { name: /Voice and tone.*UIC guideline/ })
    expect(source).toHaveAttribute('href', 'https://brand.uic.edu/messaging/voice-and-tone/')
    expect(source).toHaveAttribute('target', '_blank')
  })

  it('renders HTML in replies as inert text (no injection)', async () => {
    const evil = 'Hi <script>window.__pwned = true</script> <img src=x onerror="window.__pwned = true"> [click me](javascript:alert(1)) **<b>bold</b>**'
    refineMock.mockResolvedValueOnce({ reply: evil })
    const { user, composer, container } = renderChat()
    await user.type(composer(), '<img src=x onerror=alert(1)>{Enter}')

    const messages = await screen.findByRole('list', { name: 'Messages' })
    await within(messages).findByText(/window\.__pwned = true<\/script>/)
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img:not([src$="uic-circle-mark.png"])')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(within(messages).getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(within(messages).getByText('<b>bold</b>').tagName).toBe('STRONG')
    for (const a of container.querySelectorAll('a')) expect(a.getAttribute('href')).toMatch(/^https:\/\//)
    expect(within(messages).getByText(/click me/)).toBeInTheDocument()
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined()
  })

  it('clears the conversation after confirmation, and Cancel/Escape keep it', async () => {
    const { user, composer } = renderChat()
    await user.type(composer(), 'Question one{Enter}')
    await screen.findByText('official name')

    // Cancel keeps the conversation and returns focus.
    const clearBtn = screen.getByRole('button', { name: /clear conversation/i })
    await user.click(clearBtn)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel).toHaveFocus()
    await user.click(cancel)
    expect(screen.getByText('Question one')).toBeInTheDocument()
    expect(clearBtn).toHaveFocus()

    // Escape also cancels.
    await user.click(clearBtn)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('group', { name: /confirm clear/i })).not.toBeInTheDocument()

    await user.click(clearBtn)
    await user.click(screen.getByRole('button', { name: 'Clear chat' }))
    expect(screen.queryByText('Question one')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /how can i help/i })).toBeInTheDocument()
    expect(screen.getByText('Conversation cleared.')).toBeInTheDocument()
    expect(composer()).toHaveFocus()
  })

  it('shows failed replies as errors with a Try again action', async () => {
    refineMock.mockRejectedValueOnce({ status: 503, message: 'The service is having trouble right now.', retryable: true })
    const { user, composer } = renderChat()
    await user.type(composer(), 'Make it shorter{Enter}')

    const messages = await screen.findByRole('list', { name: 'Messages' })
    expect(await within(messages).findByText(/Sorry — The service is having trouble right now\./)).toBeInTheDocument()
    expect(screen.getByText(/^Error: Sorry/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(refineMock).toHaveBeenCalledTimes(2))
    expect(refineMock.mock.calls[1][0].message).toBe('Make it shorter')
    expect(await screen.findAllByText('official name')).toHaveLength(1)
  })

  it('offers follow-up suggestions after a reply, without repeating asked ones', async () => {
    const { user } = renderChat()
    await user.click(screen.getByRole('button', { name: STYLE_SUGGESTIONS[0] }))
    await screen.findByText('official name')
    const group = screen.getByRole('group', { name: 'Suggested follow-ups' })
    expect(within(group).queryByRole('button', { name: STYLE_SUGGESTIONS[0] })).not.toBeInTheDocument()
    await user.click(within(group).getByRole('button', { name: STYLE_SUGGESTIONS[1] }))
    expect(refineMock.mock.lastCall?.[0]).toMatchObject({ message: STYLE_SUGGESTIONS[1] })
  })

  it('shows a character counter near the 1000 character limit', async () => {
    const { user, composer } = renderChat()
    await user.click(composer())
    await user.paste('a'.repeat(799))
    expect(screen.queryByText(/\/1000/)).not.toBeInTheDocument()
    await user.paste('a'.repeat(51))
    expect(screen.getByText(/850\/1000/)).toBeInTheDocument()
    expect(composer()).toHaveAttribute('maxlength', '1000')
  })

  it('restores a persisted conversation', () => {
    localStorage.setItem(
      'uic-editorial:chat',
      JSON.stringify([
        { id: 'a', role: 'user', content: 'Earlier question', created_at: '2026-10-08T15:04:00.000Z' },
        { id: 'b', role: 'assistant', content: 'Earlier **answer**', created_at: '2026-10-08T15:04:05.000Z' },
      ]),
    )
    renderChat()
    const messages = screen.getByRole('list', { name: 'Messages' })
    expect(within(messages).getAllByRole('listitem')).toHaveLength(2)
    expect(within(messages).getByText('answer').tagName).toBe('STRONG')
    expect(messages.querySelectorAll('time')).toHaveLength(2)
  })

  it('blocks sending while an analysis is running', async () => {
    vi.mocked(analyze).mockReturnValue(new Promise(() => {}))
    localStorage.setItem('uic-editorial:text', JSON.stringify(SAMPLE_TEXT))
    function AnalyzeTrigger() {
      const { runAnalysis } = useText()
      return (
        <button type="button" onClick={() => void runAnalysis()}>
          Run analysis
        </button>
      )
    }
    const user = userEvent.setup()
    render(
      <RulesetProvider>
        <UIProvider>
          <TextProvider>
            <AnalyzeTrigger />
            <ChatInterface />
          </TextProvider>
        </UIProvider>
      </RulesetProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Run analysis' }))
    const composer = screen.getByRole('textbox', { name: /message the editor/i })
    expect(composer).toHaveAttribute('placeholder', 'Waiting for the analysis…')
    await user.type(composer, 'Make it shorter{Enter}')
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
    expect(refineMock).not.toHaveBeenCalled()
  })
})

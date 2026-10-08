/**
 * "Ask the editor" chat panel (Task 4.8, SPEC FR-11): style questions before an analysis;
 * explanations and refinements after one. Fills its container's height — header, scrolling
 * message list, composer pinned at the bottom — so it can live in a side panel or a drawer.
 */
import { ArrowDown, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useRulesets } from '../context/RulesetContext'
import { useText } from '../context/TextContext'
import { buildSuggestions, isErrorReply, MAX_MESSAGE_LENGTH, unaskedSuggestions } from './chat/chatHelpers'
import { Composer } from './chat/Composer'
import { EmptyState } from './chat/EmptyState'
import { toPlainText } from './chat/markdownParser'
import { MessageItem, TypingIndicator } from './chat/MessageItem'

export interface ChatInterfaceProps {
  /** Extra classes for the outer card (e.g. to drop the border/shadow inside a drawer). */
  className?: string
  /** When provided, a close button is shown in the header (drawer / mobile sheet). */
  onClose?: () => void
}

/** Distance (px) from the bottom within which we keep following new messages. */
const STICKY_THRESHOLD = 72

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export default function ChatInterface({ className = '', onClose }: ChatInterfaceProps = {}) {
  const { chat, chatPending, sendChat, clearChat, analysis, status, openIssues } = useText()
  // No sending while a reply is pending or an analysis is running (the reply would refer to a stale rewrite).
  const analyzing = status === 'loading'
  const busy = chatPending || analyzing
  const { audience, channel } = useRulesets()
  const titleId = useId()
  const contextId = useId()
  const confirmId = useId()

  const [draft, setDraft] = useState('')
  const [confirmingClear, setConfirmingClear] = useState(false)
  const [hasUnseen, setHasUnseen] = useState(false)
  const [announcement, setAnnouncement] = useState('')

  const scrollRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const clearBtnRef = useRef<HTMLButtonElement>(null)
  const cancelBtnRef = useRef<HTMLButtonElement>(null)
  const atBottomRef = useRef(true)
  const prevLenRef = useRef(0)

  const hasAnalysis = !!analysis
  const context = `${hasAnalysis ? 'Using your checked draft' : 'General style help'} · ${audience} · ${channel}`
  const suggestions = useMemo(
    () => buildSuggestions(analysis, { audience, channel, openIssueCount: openIssues.length }),
    [analysis, audience, channel, openIssues.length],
  )
  const followUps = useMemo(() => unaskedSuggestions(suggestions, chat).slice(0, 3), [suggestions, chat])
  const last = chat[chat.length - 1]
  const isEmpty = chat.length === 0 && !chatPending

  // ------------------------------------------------------------------ sending

  const send = useCallback(
    (text: string) => {
      const content = text.trim().slice(0, MAX_MESSAGE_LENGTH)
      if (!content || busy) return false
      atBottomRef.current = true // the user just acted: follow the conversation
      setAnnouncement('')
      setConfirmingClear(false)
      void sendChat(content)
      return true
    },
    [busy, sendChat],
  )
  // Stable identity for memoized message rows.
  const sendRef = useRef(send)
  useEffect(() => {
    sendRef.current = send
  }, [send])
  const retry = useCallback((text: string) => {
    sendRef.current(text)
  }, [])

  const sendDraft = () => {
    if (send(draft)) setDraft('')
  }
  const pickSuggestion = (prompt: string) => {
    send(prompt)
    composerRef.current?.focus()
  }

  // ------------------------------------------------------------------ scrolling

  const scrollToBottom = useCallback((smooth: boolean) => {
    const el = scrollRef.current
    if (!el) return
    if (smooth && !prefersReducedMotion() && typeof el.scrollTo === 'function') {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    } else {
      el.scrollTop = el.scrollHeight
    }
    atBottomRef.current = true
    setHasUnseen(false)
  }, [])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < STICKY_THRESHOLD
    atBottomRef.current = near
    if (near) setHasUnseen(false)
  }

  // Follow new messages, but never yank a reader who scrolled up — show a "New message" pill instead.
  useLayoutEffect(() => {
    const prevLen = prevLenRef.current
    prevLenRef.current = chat.length
    if (chat.length === 0) return
    const grew = chat.length > prevLen
    const lastMsg = chat[chat.length - 1]
    if (atBottomRef.current || (grew && lastMsg.role === 'user')) scrollToBottom(prevLen > 0)
    else if (grew) setHasUnseen(true)
  }, [chat, chatPending, scrollToBottom])

  // ------------------------------------------------------------------ announcements

  // Announce replies that arrive while mounted (not a conversation restored from storage).
  const [restoredLastId] = useState(() => chat[chat.length - 1]?.id ?? null)
  const replyAnnouncement = useMemo(() => {
    if (!last || last.role !== 'assistant' || last.id === restoredLastId) return ''
    const text = toPlainText(last.content)
    return `${isErrorReply(last) ? 'Error' : 'Editor replied'}: ${text.length > 600 ? `${text.slice(0, 600)}…` : text}`
  }, [last, restoredLastId])

  // ------------------------------------------------------------------ clear conversation

  const startClear = () => setConfirmingClear(true)
  const cancelClear = () => {
    setConfirmingClear(false)
    clearBtnRef.current?.focus()
  }
  const confirmClear = () => {
    clearChat()
    setConfirmingClear(false)
    setHasUnseen(false)
    setAnnouncement('Conversation cleared.')
    composerRef.current?.focus()
  }
  useEffect(() => {
    if (confirmingClear) cancelBtnRef.current?.focus()
  }, [confirmingClear])
  const onConfirmKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      cancelClear()
    }
  }

  // ------------------------------------------------------------------ render

  const retryTextFor = (index: number) => {
    for (let i = index - 1; i >= 0; i--) if (chat[i].role === 'user') return chat[i].content
    return undefined
  }
  const liveText = chatPending ? 'The editor is typing a reply…' : replyAnnouncement || announcement
  const showFollowUps = !isEmpty && !busy && last?.role === 'assistant' && followUps.length > 0

  return (
    <section
      aria-labelledby={titleId}
      className={`flex h-full min-h-[26rem] flex-col overflow-hidden rounded-2xl border border-black/5 bg-white shadow-sm ${className}`}
    >
      {/* Header */}
      <header className="flex items-center gap-2 border-b border-black/5 py-2 pl-4 pr-2 sm:pl-5">
        <div className="min-w-0 flex-1">
          <h2
            id={titleId}
            title={context}
            aria-describedby={contextId}
            className="truncate text-base font-semibold leading-tight text-uic-navy"
          >
            Ask the editor
          </h2>
          <span id={contextId} className="sr-only">
            {context}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {chat.length > 0 && (
            <button
              ref={clearBtnRef}
              type="button"
              onClick={startClear}
              aria-label="Clear conversation"
              title="Clear conversation"
              aria-expanded={confirmingClear}
              aria-controls={confirmingClear ? confirmId : undefined}
              className="grid size-10 place-items-center rounded-xl text-uic-steel/70 transition hover:bg-black/[0.04] hover:text-uic-steel"
            >
              <Trash2 size={17} aria-hidden="true" />
            </button>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close chat"
              className="grid size-10 place-items-center rounded-xl text-uic-steel/80 transition hover:bg-black/[0.04] hover:text-uic-steel"
            >
              <X size={18} aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      {/* Clear confirmation */}
      {confirmingClear && (
        <div
          id={confirmId}
          role="group"
          aria-label="Confirm clear conversation"
          onKeyDown={onConfirmKeyDown}
          className="flex flex-wrap items-center gap-2 border-b border-uic-red/15 bg-[#fff5f7] px-4 py-2.5 transition duration-200 starting:-translate-y-1 starting:opacity-0 sm:px-5"
        >
          <p className="mr-auto text-sm text-uic-steel">
            <span className="font-medium">Clear this conversation?</span>{' '}
            <span className="text-uic-steel/80">Your draft and rewrite stay as they are.</span>
          </p>
          <button
            ref={cancelBtnRef}
            type="button"
            onClick={cancelClear}
            className="min-h-10 rounded-xl border border-black/10 bg-white px-3.5 text-sm font-medium text-uic-steel transition hover:bg-black/[0.03]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirmClear}
            className="min-h-10 rounded-xl bg-uic-red px-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-uic-red/90"
          >
            Clear chat
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          role="region"
          aria-label="Conversation"
          tabIndex={0}
          className="h-full overflow-y-auto overscroll-contain px-3 py-4 focus-visible:outline-offset-[-2px] sm:px-4"
        >
          {isEmpty ? (
            <EmptyState hasAnalysis={hasAnalysis} suggestions={suggestions.slice(0, 3)} onPick={pickSuggestion} disabled={busy} />
          ) : (
            <ol className="space-y-4" aria-label="Messages">
              {chat.map((m, i) => (
                <MessageItem
                  key={m.id}
                  message={m}
                  retryText={isErrorReply(m) ? retryTextFor(i) : undefined}
                  onRetry={retry}
                  retryDisabled={busy}
                />
              ))}
              {chatPending && <TypingIndicator />}
            </ol>
          )}
        </div>

        {hasUnseen && chat.length > 0 && (
          <button
            type="button"
            onClick={() => scrollToBottom(true)}
            className="absolute bottom-3 left-1/2 inline-flex min-h-9 -translate-x-1/2 items-center gap-1.5 rounded-full bg-uic-navy px-3.5 text-xs font-medium text-white shadow-lg transition hover:bg-uic-navy/90 starting:translate-y-2 starting:opacity-0"
          >
            New message
            <ArrowDown size={14} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-black/5 bg-white px-3 pt-2.5 pb-3 sm:px-4">
        {showFollowUps && (
          <div role="group" aria-label="Suggested follow-ups" className="-mx-1 mb-2 flex gap-1.5 overflow-x-auto px-1 pb-0.5 [scrollbar-width:none]">
            {followUps.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => pickSuggestion(s)}
                className="inline-flex min-h-9 shrink-0 items-center rounded-full border border-uic-navy/15 bg-white px-3 text-xs font-medium whitespace-nowrap text-uic-navy transition hover:border-uic-navy/30 hover:bg-uic-navy/[0.04]"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <Composer
          ref={composerRef}
          value={draft}
          onChange={setDraft}
          onSend={sendDraft}
          pending={busy}
          placeholder={analyzing ? 'Waiting for the analysis…' : hasAnalysis ? 'Ask about a change or request an edit…' : 'Ask about UIC style…'}
        />
      </div>

      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {liveText}
      </div>
    </section>
  )
}

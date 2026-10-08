import { LoaderCircle, MessageSquareText } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useText } from '../../context/TextContext'
import ChatInterface from '../ChatInterface'
import ErrorBoundary from './ErrorBoundary'
import { useFocusTrap } from './useFocusTrap'

export const CHAT_DRAWER_ID = 'chat-drawer'

/**
 * Floating launcher visibility below lg: hidden while the page scrolls down (so it never sits on
 * top of what the user is reading), shown again on scroll up, near the top and at the very bottom
 * (where the footer reserves room for it).
 */
function useHideOnScroll(): boolean {
  const [hidden, setHidden] = useState(false)
  useEffect(() => {
    let lastY = window.scrollY
    let frame = 0
    const update = () => {
      frame = 0
      const y = window.scrollY
      const atBottom = y + window.innerHeight >= document.documentElement.scrollHeight - 48
      if (y < 64 || atBottom) setHidden(false)
      else if (y > lastY + 4) setHidden(true)
      else if (y < lastY - 4) setHidden(false)
      lastY = y
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])
  return hidden
}

interface ChatDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * "Ask the editor": chat panel plus the floating launcher used below lg (from lg up the launcher
 * lives in the sticky header). Right-side drawer from md up, bottom sheet on phones. Stays mounted
 * while closed (inert) so an unsent message survives.
 */
export default function ChatDrawer({ open, onOpenChange }: ChatDrawerProps) {
  const { chat, chatPending } = useText()
  const panelRef = useRef<HTMLDivElement>(null)
  const fabRef = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => onOpenChange(false), [onOpenChange])
  const scrolledAway = useHideOnScroll()

  useFocusTrap(panelRef, open, {
    onEscape: close,
    lockScroll: true,
    initialFocus: (el) => el.querySelector<HTMLElement>('textarea, input[type="text"]'),
    // The launcher that opened the drawer may be gone after a resize across lg: fall back to the visible one.
    restoreFocusFallback: () =>
      [fabRef.current, document.querySelector<HTMLElement>(`header [aria-controls="${CHAT_DRAWER_ID}"]`)].find(
        (el) => !!el && el.getClientRects().length > 0,
      ) ?? null,
  })

  const count = chat.length

  return (
    <>
      <button
        ref={fabRef}
        type="button"
        onClick={() => onOpenChange(true)}
        aria-expanded={open}
        aria-controls={CHAT_DRAWER_ID}
        aria-haspopup="dialog"
        aria-label={count > 0 ? `Ask the editor (${count} messages)` : 'Ask the editor'}
        className={`fixed bottom-5 right-4 z-40 inline-flex size-14 items-center justify-center gap-2 rounded-full bg-uic-navy text-sm font-semibold text-white shadow-lg shadow-uic-navy/25 ring-1 ring-white/10 transition duration-200 hover:bg-uic-navy/95 hover:shadow-xl sm:bottom-6 sm:right-6 sm:h-12 sm:w-auto sm:pl-4 sm:pr-5 lg:hidden ${
          open
            ? 'pointer-events-none translate-y-2 opacity-0'
            : scrolledAway
              ? 'pointer-events-none translate-y-[calc(100%+2rem)] opacity-0 focus-visible:pointer-events-auto focus-visible:translate-y-0 focus-visible:opacity-100'
              : 'opacity-100'
        }`}
      >
        {chatPending ? (
          <LoaderCircle size={20} aria-hidden="true" className="animate-spin" />
        ) : (
          <MessageSquareText size={20} aria-hidden="true" />
        )}
        <span aria-hidden="true" className="hidden sm:inline">
          Ask the editor
        </span>
        {count > 0 && (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full bg-uic-red px-1.5 text-[11px] font-semibold tabular-nums ring-2 ring-white sm:static sm:bg-white/15 sm:text-xs sm:font-medium sm:ring-0"
          >
            {count}
          </span>
        )}
      </button>

      <div className={`fixed inset-0 z-50 ${open ? '' : 'pointer-events-none'}`}>
        <div
          aria-hidden="true"
          onClick={close}
          className={`absolute inset-0 bg-uic-navy/25 backdrop-blur-[1px] transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0'}`}
        />
        <div
          ref={panelRef}
          id={CHAT_DRAWER_ID}
          role="dialog"
          aria-modal="true"
          aria-label="Ask the editor"
          aria-hidden={!open}
          inert={!open}
          tabIndex={-1}
          // Visibility flips instantly on open (so focus can move in right away) but waits for the slide-out on close.
          className={`absolute inset-x-0 bottom-0 flex h-[92dvh] flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl outline-none duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] md:inset-y-0 md:left-auto md:right-0 md:h-full md:w-[440px] md:rounded-none md:rounded-l-3xl lg:w-[460px] ${
            open
              ? 'visible translate-y-0 transition-[translate] md:translate-x-0'
              : 'invisible translate-y-full transition-[translate,visibility] md:translate-x-full md:translate-y-0'
          }`}
        >
          <div aria-hidden="true" className="flex shrink-0 justify-center pb-1 pt-2.5 md:hidden">
            <span className="h-1.5 w-10 rounded-full bg-black/15" />
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <ErrorBoundary variant="section" label="the chat">
              <ChatInterface onClose={close} className="h-full rounded-none border-0 shadow-none" />
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </>
  )
}

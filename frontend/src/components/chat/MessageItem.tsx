import { AlertCircle, BookOpen, Check, Copy, ExternalLink, RotateCcw } from 'lucide-react'
import { memo, useEffect, useRef, useState } from 'react'
import type { ChatMessage, GuidelineChunk } from '../../types/api'
import { formatTime, guidelineSources, isErrorReply } from './chatHelpers'
import Markdown from './Markdown'
import { toPlainText } from './markdownParser'

/** The official UIC circle mark (public/brand) as the assistant's avatar. Decorative. */
export function UicMark({ className = '' }: { className?: string }) {
  return (
    <img
      src={`${import.meta.env.BASE_URL}brand/uic-circle-mark.png`}
      alt=""
      aria-hidden="true"
      width={28}
      height={28}
      draggable={false}
      className={`size-7 shrink-0 select-none rounded-full ${className}`}
    />
  )
}

interface MessageItemProps {
  message: ChatMessage & { guidelines?: GuidelineChunk[] | null }
  /** For failed replies: the question to resend, and the (stable) resend callback. */
  retryText?: string
  onRetry?: (text: string) => void
  retryDisabled?: boolean
}

export const MessageItem = memo(function MessageItem({ message, retryText, onRetry, retryDisabled }: MessageItemProps) {
  const time = formatTime(message.created_at)

  if (message.role === 'user') {
    return (
      <li className="transition-[opacity,translate] duration-200 ease-out starting:translate-y-1 starting:opacity-0 flex flex-col items-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-uic-navy px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-white shadow-sm [overflow-wrap:anywhere] sm:text-[15px]">
          <span className="sr-only">You said: </span>
          {message.content}
        </div>
        {time && (
          <time dateTime={message.created_at} className="mt-1 mr-1 text-[11px] text-uic-steel/70">
            {time}
          </time>
        )}
      </li>
    )
  }

  const failed = isErrorReply(message)
  const sources = failed ? [] : guidelineSources(message)

  return (
    <li className="transition-[opacity,translate] duration-200 ease-out starting:translate-y-1 starting:opacity-0 flex items-start gap-2.5">
      <UicMark className="mt-0.5" />
      <div className="group min-w-0 max-w-[92%] flex-1 sm:flex-none">
        <div
          className={`rounded-2xl rounded-tl-md border px-4 py-3 text-sm leading-relaxed text-uic-steel shadow-sm sm:text-[15px] ${
            failed ? 'border-uic-red/25 bg-[#fff5f7]' : 'border-black/5 bg-white'
          }`}
        >
          <span className="sr-only">Editor replied: </span>
          {failed ? (
            <div className="flex items-start gap-2">
              <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-uic-red" />
              <p>{message.content}</p>
            </div>
          ) : (
            <Markdown text={message.content} />
          )}

          {sources.length > 0 && (
            <div className="mt-3 border-t border-black/5 pt-2.5">
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-uic-steel/70">Sources</p>
              <ul className="flex flex-wrap gap-1.5">
                {sources.map((s) => (
                  <li key={s.url}>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-full border border-uic-navy/15 bg-uic-navy/[0.04] px-2.5 py-1 text-xs font-medium text-uic-navy transition-colors hover:border-uic-navy/30 hover:bg-uic-navy/[0.08]"
                    >
                      <BookOpen size={12} aria-hidden="true" />
                      {s.title}
                      <ExternalLink size={11} aria-hidden="true" className="opacity-60" />
                      <span className="sr-only"> (UIC guideline, opens in a new tab)</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="mt-1 ml-1 flex min-h-6 items-center gap-1 text-[11px] text-uic-steel/70">
          {time && <time dateTime={message.created_at}>{time}</time>}
          {failed && onRetry && retryText ? (
            <button
              type="button"
              onClick={() => onRetry(retryText)}
              disabled={retryDisabled}
              className="ml-1 inline-flex items-center gap-1 rounded-full px-2 py-1 font-medium text-uic-navy transition-colors hover:bg-uic-navy/[0.06] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw size={12} aria-hidden="true" />
              Try again
            </button>
          ) : (
            !failed && <CopyButton text={message.content} />
          )}
        </div>
      </div>
    </li>
  )
})

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (typeof navigator === 'undefined' || !navigator.clipboard) return null
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(toPlainText(text))
      setCopied(true)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="ml-1 inline-flex items-center gap-1 rounded-full px-2 py-1 font-medium text-uic-steel/70 transition hover:bg-black/[0.04] hover:text-uic-navy pointer-fine:opacity-0 pointer-fine:group-hover:opacity-100 pointer-fine:group-focus-within:opacity-100"
    >
      {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
      <span aria-live="polite">{copied ? 'Copied' : 'Copy'}</span>
    </button>
  )
}

/** Animated "editor is typing" bubble shown while a reply is pending. */
export function TypingIndicator() {
  return (
    <li className="transition-[opacity,translate] duration-200 ease-out starting:translate-y-1 starting:opacity-0 flex items-start gap-2.5" aria-hidden="true">
      <UicMark className="mt-0.5" />
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-md border border-black/5 bg-white px-4 py-3.5 shadow-sm">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1.5 animate-bounce rounded-full bg-uic-navy/50"
            style={{ animationDelay: `${delay}ms`, animationDuration: '1s' }}
          />
        ))}
      </div>
    </li>
  )
}

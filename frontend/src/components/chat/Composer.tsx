import { ArrowUp } from 'lucide-react'
import { useId, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent, type Ref } from 'react'
import { COUNTER_THRESHOLD, MAX_MESSAGE_LENGTH } from './chatHelpers'

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  pending: boolean
  placeholder: string
  ref?: Ref<HTMLTextAreaElement>
}

const MAX_HEIGHT_PX = 160

/** Auto-growing message box. Enter sends, Shift+Enter inserts a newline. The placeholder never wraps (ellipsis instead). */
export function Composer({ value, onChange, onSend, pending, placeholder, ref: forwardedRef }: ComposerProps) {
  const inputId = useId()
  const hintId = useId()
  const counterId = useId()
  const localRef = useRef<HTMLTextAreaElement | null>(null)
  const canSend = value.trim().length > 0 && !pending
  const showCounter = value.length >= COUNTER_THRESHOLD
  const remaining = MAX_MESSAGE_LENGTH - value.length

  // Re-measure when the text or placeholder changes, and when the viewport resizes (the drawer
  // changes width across breakpoints, which re-wraps the text).
  useLayoutEffect(() => {
    const fit = () => {
      const el = localRef.current
      if (!el) return
      el.style.height = 'auto'
      const next = Math.min(el.scrollHeight, MAX_HEIGHT_PX)
      if (next > 0) el.style.height = `${next}px`
      el.style.overflowY = el.scrollHeight > MAX_HEIGHT_PX ? 'auto' : 'hidden'
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [value, placeholder])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (canSend) onSend()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return
    e.preventDefault()
    if (canSend) onSend()
  }

  const setRefs = (el: HTMLTextAreaElement | null) => {
    localRef.current = el
    if (typeof forwardedRef === 'function') forwardedRef(el)
    else if (forwardedRef) forwardedRef.current = el
  }

  return (
    <form onSubmit={submit} className="w-full">
      <div className="flex items-end gap-2 rounded-2xl border border-black/10 bg-white p-1.5 pl-3.5 shadow-sm transition focus-within:border-uic-navy/40 focus-within:ring-4 focus-within:ring-uic-navy/10">
        <label htmlFor={inputId} className="sr-only">
          Message the editor
        </label>
        <textarea
          id={inputId}
          ref={setRefs}
          rows={1}
          value={value}
          maxLength={MAX_MESSAGE_LENGTH}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          aria-describedby={showCounter ? `${hintId} ${counterId}` : hintId}
          className="block max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2 text-sm leading-6 text-uic-steel outline-none placeholder:truncate placeholder:text-uic-steel/70 focus-visible:outline-none sm:text-[15px]"
        />
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Send message"
          title="Send (Enter)"
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-uic-navy text-white shadow-sm transition hover:bg-uic-navy/90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100"
        >
          <ArrowUp size={18} strokeWidth={2.5} aria-hidden="true" />
        </button>
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-3 px-1 text-[11px] text-uic-steel/70">
        <span id={hintId}>
          <kbd className="font-sans font-medium">Enter</kbd> to send · <kbd className="font-sans font-medium">Shift + Enter</kbd> for a new line
        </span>
        {showCounter && (
          <span
            id={counterId}
            className={`shrink-0 tabular-nums font-medium ${remaining <= 0 ? 'text-uic-red' : remaining <= 100 ? 'text-[#B45309]' : ''}`}
          >
            {value.length}/{MAX_MESSAGE_LENGTH}
            <span className="sr-only"> characters ({Math.max(remaining, 0)} left)</span>
          </span>
        )}
      </div>
    </form>
  )
}

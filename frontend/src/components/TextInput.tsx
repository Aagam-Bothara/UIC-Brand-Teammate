import { ClipboardPaste, Eraser, Undo2 } from 'lucide-react'
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react'
import { MAX_CHARS, MAX_WORDS } from '../config/rulesets'
import { useRulesets } from '../context/RulesetContext'
import { useText } from '../context/TextContext'
import { useUI } from '../context/UIContext'
import type { DemoSample } from '../data/demoSamples'
import Kbd from './input/Kbd'
import SampleMenu from './input/SampleMenu'
import { useAnalyzeGate } from './input/useAnalyzeGate'
import { canReadClipboard, cx, fmt, meterTone, modKeyLabel, plural } from './input/utils'
import WordMeter from './input/WordMeter'

interface UndoState {
  message: string
  previous: string
}

const UNDO_MS = 10000

/** Windows / old-Mac line endings → \n, which is what a textarea reports back (keeps offsets stable). */
const normalizeNewlines = (s: string) => s.replace(/\r\n?/g, '\n')

const quietBtn =
  'inline-flex min-h-10 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-uic-steel/75 transition duration-150 ease-out hover:bg-black/[0.04] hover:text-uic-navy active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent'

/**
 * Task 4.4 — the writing surface. Auto-growing textarea bound to the draft in TextContext, a subtle
 * word counter against the 5,000-word limit (SPEC FR-1), quiet sample/paste/clear helpers with undo,
 * and a Cmd/Ctrl+Enter shortcut that runs the analysis.
 */
export default function TextInput() {
  const { text, setText, isStale, status, runAnalysis } = useText()
  const { notify } = useUI()
  const { setAudience, setChannel } = useRulesets()
  const { words, chars, overLimit, reason, canAnalyze } = useAnalyzeGate()
  const [undo, setUndo] = useState<UndoState | null>(null)
  const [clipboardOk] = useState(canReadClipboard)
  const [mod] = useState(modKeyLabel)
  const ref = useRef<HTMLTextAreaElement>(null)
  const uid = useId()
  const titleId = `${uid}-title`
  const countId = `${uid}-count`

  const tone = meterTone(words, MAX_WORDS, overLimit)

  // Auto-grow: fit the content, never below the minimum (CSS max-height caps it).
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    if (el.scrollHeight > 0) el.style.height = `${el.scrollHeight + 2}px`
  }, [text])

  // The undo offer fades after a while.
  useEffect(() => {
    if (!undo) return
    const t = setTimeout(() => setUndo(null), UNDO_MS)
    return () => clearTimeout(t)
  }, [undo])

  const replaceText = (next: string, message: string | null) => {
    setUndo(message && text.trim() && text !== next ? { message, previous: text } : null)
    setText(next)
    ref.current?.focus()
  }

  const loadSample = (sample: DemoSample) => {
    replaceText(sample.text, 'Sample loaded.')
    setAudience(sample.audience)
    setChannel(sample.channel)
    notify(`Loaded “${sample.title}” (${sample.audience} · ${sample.channel}). Press Analyze.`, 'success')
  }

  const clear = () => replaceText('', 'Draft cleared.')

  const restore = () => {
    if (!undo) return
    setText(undo.previous)
    setUndo(null)
    ref.current?.focus()
  }

  const paste = async () => {
    try {
      const clip = normalizeNewlines(await navigator.clipboard.readText())
      if (!clip) {
        notify('Your clipboard is empty.', 'info')
        return
      }
      const el = ref.current
      const start = el?.selectionStart ?? text.length
      const end = el?.selectionEnd ?? text.length
      const next = text.slice(0, start) + clip + text.slice(end)
      // Pasting over a selection replaces text: offer the same undo as Clear / Sample.
      setUndo(end > start ? { message: 'Selection replaced.', previous: text } : null)
      setText(next)
      requestAnimationFrame(() => {
        if (!el) return
        el.focus()
        el.setSelectionRange(start + clip.length, start + clip.length)
      })
    } catch {
      notify(`Couldn’t read the clipboard. Click in the box and press ${mod}+V instead.`, 'error')
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Enter' || !(e.metaKey || e.ctrlKey)) return
    // Enter during IME composition (Japanese, Chinese, Korean…) confirms the composition; it must
    // not submit a half-typed draft.
    if (e.nativeEvent.isComposing || e.keyCode === 229) return
    e.preventDefault()
    if (status === 'loading' || e.repeat) return
    if (canAnalyze) void runAnalysis()
    else if (reason) notify(reason, 'info')
  }

  const wordsOver = words - MAX_WORDS
  let limitMessage: string | null = null
  if (wordsOver > 0) {
    limitMessage = `${plural(wordsOver, 'word')} over the ${fmt(MAX_WORDS)}-word limit. Try one section at a time.`
  } else if (chars > MAX_CHARS) {
    limitMessage = `Over the ${fmt(MAX_CHARS)}-character limit. Try one section at a time.`
  } else if (tone === 'near') {
    limitMessage = `Getting close to the ${fmt(MAX_WORDS)}-word limit.`
  }

  const hasText = text.length > 0
  const showStale = isStale && status !== 'loading'

  return (
    <section aria-labelledby={titleId} className="rounded-2xl border border-black/5 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 items-center gap-2">
          <h2 id={titleId} className="text-base font-semibold text-uic-navy">
            Your draft
          </h2>
          {showStale && (
            <span className="rounded-full bg-uic-beach px-2 py-0.5 text-[11px] font-medium text-[#8A4B0B] transition duration-200 ease-out starting:opacity-0">
              Edited since last analysis
            </span>
          )}
        </div>
        <div className="-mr-2 flex items-center" role="toolbar" aria-label="Draft tools">
          <SampleMenu onPick={loadSample} className={quietBtn} />
          {clipboardOk && (
            <button type="button" onClick={paste} className={quietBtn}>
              <ClipboardPaste size={15} aria-hidden="true" />
              Paste
            </button>
          )}
          <button type="button" onClick={clear} disabled={!hasText} className={quietBtn}>
            <Eraser size={15} aria-hidden="true" />
            Clear
          </button>
        </div>
      </div>

      {undo && (
        <div
          role="status"
          className="mt-2 flex items-center justify-between gap-3 rounded-lg bg-uic-navy px-3 py-1.5 text-[13px] text-white transition duration-200 ease-out starting:opacity-0"
        >
          <span>{undo.message}</span>
          <button
            type="button"
            onClick={restore}
            className="inline-flex min-h-8 items-center gap-1.5 rounded-md px-2 font-medium text-white hover:bg-white/10 focus-visible:outline-white"
          >
            <Undo2 size={14} aria-hidden="true" />
            Undo
          </button>
        </div>
      )}

      <textarea
        ref={ref}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          if (undo) setUndo(null)
        }}
        onKeyDown={onKeyDown}
        rows={10}
        spellCheck
        aria-labelledby={titleId}
        aria-describedby={countId}
        aria-invalid={overLimit || undefined}
        aria-keyshortcuts="Meta+Enter Control+Enter"
        placeholder="Paste or type your message…"
        className={cx(
          'mt-3 block max-h-[70vh] min-h-[14rem] w-full resize-none rounded-xl border px-4 py-3 text-[15px] leading-relaxed text-uic-steel',
          'placeholder:text-uic-steel/50 transition-[border-color,box-shadow,background-color] duration-150 ease-out',
          'focus:outline-none focus-visible:outline-none focus:ring-4',
          overLimit
            ? 'border-uic-red/60 bg-uic-red/[0.02] focus:border-uic-red focus:ring-uic-red/10'
            : 'border-black/10 bg-uic-expo/40 hover:border-black/20 focus:border-uic-navy/60 focus:bg-white focus:ring-uic-navy/10',
        )}
      />

      {/* One quiet line: meter, count, shortcut */}
      <div className="mt-2 flex items-center gap-3 text-xs text-uic-steel/70">
        <div className="w-16 shrink-0 sm:w-24">
          <WordMeter words={words} tone={tone} />
        </div>
        <p id={countId} data-testid="draft-counts" className="tabular-nums" title={plural(chars, 'character')}>
          <span className={cx(tone === 'over' ? 'font-medium text-uic-red' : tone === 'near' ? 'font-medium text-[#8A4B0B]' : undefined)}>
            {fmt(words)}
          </span>{' '}
          / {fmt(MAX_WORDS)} words
          {chars > MAX_CHARS * 0.85 && <span> · {plural(chars, 'character')}</span>}
        </p>
        <p className="ml-auto hidden items-center gap-1 sm:flex">
          <Kbd>{mod}</Kbd>
          <Kbd>Enter</Kbd>
          <span className="ml-0.5">to analyze</span>
        </p>
      </div>
      {limitMessage && (
        <p
          role={tone === 'over' ? 'alert' : 'status'}
          className={cx('mt-1.5 text-xs font-medium', tone === 'over' ? 'text-[#A3001F]' : 'text-[#8A4B0B]')}
        >
          {limitMessage}
        </p>
      )}
    </section>
  )
}

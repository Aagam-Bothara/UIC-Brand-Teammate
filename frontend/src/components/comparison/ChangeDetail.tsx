import { ArrowDown, BookOpen, Check, ChevronLeft, ChevronRight, ExternalLink, RotateCcw, X } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import type { ChangeDecision } from '../../lib/changes'
import type { Change, Issue, RulesetInfo } from '../../types/api'
import { SEVERITY_STYLE, findChangeAnchor, prefersReducedMotion, snippet, tint, type ChangeState } from './utils'

interface ChangeDetailProps {
  change: Change
  index: number
  total: number
  state: ChangeState
  ruleset: RulesetInfo
  issues: Issue[]
  /** Positioned relative to this element; the change's anchor is looked up inside it. */
  containerRef: RefObject<HTMLDivElement | null>
  onClose: (returnFocus: boolean) => void
  onDecide: (decision: ChangeDecision | null) => void
  onStep: (delta: -1 | 1) => void
}

const GAP = 8
const MIN_HEIGHT = 220

const SHEET_QUERY = '(max-width: 639.98px)'

/**
 * Phones show the popover as a fixed bottom sheet. It must be portalled to <body>: the comparison
 * card is a CSS size container, which becomes the containing block for `position: fixed`
 * descendants and pushed the sheet off-screen.
 */
function useIsSheet(): boolean {
  const get = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(SHEET_QUERY).matches
  const [sheet, setSheet] = useState(get)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(SHEET_QUERY)
    const on = () => setSheet(mq.matches)
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  return sheet
}

/** Bottom edge of a sticky/fixed page header, so an upward-flipped popover isn't hidden under it. */
function stickyHeaderBottom(): number {
  const header = document.querySelector('header')
  if (!header) return 0
  const { position } = getComputedStyle(header)
  return position === 'sticky' || position === 'fixed' ? Math.max(0, header.getBoundingClientRect().bottom) : 0
}

const STATUS_COPY: Record<ChangeState, (ruleset: string) => string> = {
  applied: (r) => `Shown because ${r} is on.`,
  hidden: (r) => `Hidden because ${r} is off. Accept it to keep it anyway.`,
  accepted: (r) => `You accepted this change — it stays even when ${r} is off.`,
  rejected: () => 'You rejected this change — your original wording is kept.',
}

/**
 * Explanation popover for one change (FR-9) with individual accept / reject (FR-10).
 * Anchored under the change on larger screens; a bottom sheet on phones. Non-modal: Esc or a click
 * outside closes it.
 */
export default function ChangeDetail({
  change, index, total, state, ruleset, issues, containerRef, onClose, onDecide, onStep,
}: ChangeDetailProps) {
  const popRef = useRef<HTMLDivElement>(null)
  const sheet = useIsSheet()
  const [pos, setPos] = useState<{ top: number; left: number; maxHeight: number | null } | null>(null)
  const color = ruleset.highlight_color
  const guidelineUrl = change.guideline_url ?? issues.find((i) => i.guideline_url)?.guideline_url ?? null
  const guidelineTitle =
    change.guideline_title ?? issues.find((i) => i.guideline_title)?.guideline_title ?? 'UIC brand guidelines'

  const place = useCallback(() => {
    const wrap = containerRef.current
    const pop = popRef.current
    if (!wrap || !pop) return
    const anchor = findChangeAnchor(wrap, change.change_id)
    const w = wrap.getBoundingClientRect()
    const rects = anchor ? anchor.getClientRects() : null
    if (!anchor || !rects || rects.length === 0) {
      setPos({ top: 0, left: 0, maxHeight: null })
      return
    }
    const first = rects[0]
    const last = rects[rects.length - 1]
    // While the change is scrolled out of its pane, stick to the pane's visible edge instead of
    // floating over the controls (or the page header) above/below the pane.
    const clip = anchor.closest('[data-pane-scroll]')?.getBoundingClientRect()
    const clampY = (y: number) => (clip ? Math.min(Math.max(y, clip.top), clip.bottom) : y)
    const refTop = clampY(first.top)
    const refBottom = clampY(last.bottom)
    const popW = pop.offsetWidth
    // Natural content height (scrollHeight ignores a max-height applied on a previous pass).
    const popH = Math.max(pop.scrollHeight, pop.offsetHeight)
    const left = Math.max(0, Math.min(first.left - w.left, w.width - popW))
    const spaceBelow = window.innerHeight - refBottom - GAP * 2
    const spaceAbove = refTop - stickyHeaderBottom() - GAP * 2
    // Prefer below; flip above when only that side fits. When neither fits, use the roomier side
    // and cap the height (the popover scrolls) so its actions never end up off-screen.
    let above = false
    let maxHeight: number | null = null
    if (popH > spaceBelow) {
      if (popH <= spaceAbove) above = true
      else {
        above = spaceAbove > spaceBelow
        maxHeight = Math.max(MIN_HEIGHT, above ? spaceAbove : spaceBelow)
      }
    }
    const h = maxHeight === null ? popH : Math.min(popH, maxHeight)
    setPos({ top: above ? refTop - w.top - h - GAP : refBottom - w.top + GAP, left, maxHeight })
  }, [change.change_id, containerRef])

  // Bring the change into view, then anchor to it.
  useLayoutEffect(() => {
    const anchor = findChangeAnchor(containerRef.current, change.change_id)
    anchor?.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    place()
  }, [change.change_id, containerRef, place])

  // Follow the anchor while panes scroll or the window resizes.
  useEffect(() => {
    let frame = 0
    const schedule = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(place)
    }
    // Capture phase so scrolling inside either pane is seen too.
    window.addEventListener('scroll', schedule, true)
    window.addEventListener('resize', schedule)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', schedule, true)
      window.removeEventListener('resize', schedule)
    }
  }, [place])

  // Move focus into the popover when it opens (or switches change from outside), with a soft entrance.
  useEffect(() => {
    const pop = popRef.current
    if (!pop) return
    if (!pop.contains(document.activeElement)) pop.focus({ preventScroll: true })
    if (typeof pop.animate === 'function' && !prefersReducedMotion()) {
      pop.animate([{ opacity: 0, transform: 'translateY(4px) scale(0.98)' }, { opacity: 1, transform: 'none' }], {
        duration: 180,
        easing: 'ease-out',
      })
    }
  }, [change.change_id])

  // Esc closes from anywhere; a click outside (that isn't another change) closes without moving focus.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault()
        onClose(true)
      }
    }
    const onPointer = (e: PointerEvent) => {
      const t = e.target as Element | null
      if (!t || popRef.current?.contains(t) || t.closest?.('[data-change-trigger], del[data-anchor]')) return
      onClose(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [onClose])

  const before = change.original_text
  const after = change.rewritten_text
  const accepted = state === 'accepted'
  const rejected = state === 'rejected'
  const decided = accepted || rejected
  const iconBtn =
    'inline-flex h-9 w-9 items-center justify-center rounded-lg text-uic-steel/70 transition hover:bg-black/5 hover:text-uic-navy disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent'

  const dialog = (
    <div
      ref={popRef}
      role="dialog"
      aria-modal="false"
      aria-label={`${ruleset.ruleset_name} change, ${index + 1} of ${total}`}
      tabIndex={-1}
      data-testid="change-detail"
      style={
        {
          '--pop-top': `${pos?.top ?? 0}px`,
          '--pop-left': `${pos?.left ?? 0}px`,
          '--pop-max-h': pos?.maxHeight ? `${pos.maxHeight}px` : 'none',
        } as CSSProperties
      }
      className={`fixed inset-x-3 bottom-3 z-[45] max-h-[75vh] overscroll-contain overflow-y-auto rounded-2xl border border-black/10 bg-white shadow-2xl ring-1 ring-black/5 outline-none sm:absolute sm:inset-x-auto sm:top-[var(--pop-top)] sm:bottom-auto sm:left-[var(--pop-left)] sm:max-h-[var(--pop-max-h)] sm:w-[23rem] sm:max-w-full sm:shadow-xl ${
        pos ? '' : 'sm:opacity-0'
      }`}
    >
      <div className="h-1 rounded-t-2xl" style={{ backgroundColor: color }} aria-hidden="true" />
      <div className="p-4">
        <div className="flex items-center gap-2">
          <h3 className="flex min-w-0 flex-1 items-center gap-2">
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium text-uic-navy"
              style={{ backgroundColor: tint(color, '1F') }}
            >
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              {ruleset.ruleset_name}
              <span className="sr-only">&nbsp;change</span>
            </span>
            <span className="text-xs font-normal text-uic-steel/70 tabular-nums">
              {index + 1} of {total}
            </span>
          </h3>
          <button type="button" className={iconBtn} onClick={() => onStep(-1)} disabled={index === 0} aria-label="Previous change">
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <button type="button" className={iconBtn} onClick={() => onStep(1)} disabled={index >= total - 1} aria-label="Next change">
            <ChevronRight size={18} aria-hidden="true" />
          </button>
          <button type="button" className={iconBtn} onClick={() => onClose(true)} aria-label="Close details">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="mt-3 rounded-xl border border-black/5 bg-uic-expo/60 p-3 text-sm leading-relaxed">
          <p className="text-[11px] font-medium tracking-wide text-uic-steel/70 uppercase">Before</p>
          <p className="mt-0.5 break-words whitespace-pre-wrap text-uic-steel/80">
            {before.trim() ? (
              <del className="decoration-2" style={{ textDecorationColor: color }}>
                {before}
              </del>
            ) : (
              <span className="italic">{before ? snippet(before) : '(nothing — new text added)'}</span>
            )}
          </p>
          <ArrowDown size={14} aria-hidden="true" className="my-1.5 text-uic-steel/50" />
          <p className="text-[11px] font-medium tracking-wide text-uic-steel/70 uppercase">After</p>
          <p className="mt-0.5 break-words whitespace-pre-wrap text-uic-steel">
            {after.trim() ? (
              <ins className="rounded-[3px] px-px no-underline" style={{ backgroundColor: tint(color, '26'), borderBottom: `2px solid ${color}` }}>
                {after}
              </ins>
            ) : (
              <span className="italic text-uic-steel/80">{after ? snippet(after) : '(removed)'}</span>
            )}
          </p>
        </div>

        <p className="mt-3 text-sm leading-relaxed text-uic-steel">{change.explanation}</p>

        {issues.length > 0 && (
          <ul className="mt-3 space-y-1.5" aria-label="Related issues">
            {issues.map((issue) => {
              const sev = SEVERITY_STYLE[issue.severity]
              return (
                <li key={issue.issue_id} className="flex items-start gap-2 text-[13px] leading-snug text-uic-steel/80">
                  <span
                    className="mt-px shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    style={{ color: sev.color, backgroundColor: tint(sev.color, '14') }}
                  >
                    {sev.label}
                    <span className="sr-only"> severity</span>
                  </span>
                  <span>{issue.message}</span>
                </li>
              )
            })}
          </ul>
        )}

        {guidelineUrl && (
          <a
            href={guidelineUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 flex items-center gap-2 rounded-lg px-2 py-1.5 -mx-2 text-sm font-medium text-uic-navy underline-offset-2 transition hover:bg-uic-navy/5 hover:underline"
          >
            <BookOpen size={16} aria-hidden="true" className="shrink-0" />
            <span className="min-w-0 flex-1">{guidelineTitle}</span>
            <ExternalLink size={14} aria-hidden="true" className="shrink-0 opacity-70" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}

        <p className="mt-3 flex items-center gap-2 text-xs text-uic-steel/80">
          <span
            aria-hidden="true"
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: accepted ? '#00966C' : rejected ? '#6B7280' : state === 'applied' ? color : 'transparent', border: `1.5px solid ${state === 'hidden' ? color : 'transparent'}` }}
          />
          {STATUS_COPY[state](ruleset.ruleset_name)}
        </p>

        <div className="mt-3 flex flex-wrap gap-2 border-t border-black/5 pt-3">
          <button
            type="button"
            aria-pressed={accepted}
            onClick={() => onDecide(accepted ? null : 'accepted')}
            className={`inline-flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition active:scale-[0.98] ${
              accepted ? 'bg-[#00785A] text-white shadow-sm hover:bg-[#00785A]/90' : 'border border-black/10 bg-white text-uic-navy hover:bg-black/[0.03]'
            }`}
          >
            <Check size={16} aria-hidden="true" />
            {accepted ? 'Accepted' : 'Accept'}
          </button>
          <button
            type="button"
            aria-pressed={rejected}
            onClick={() => onDecide(rejected ? null : 'rejected')}
            className={`inline-flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition active:scale-[0.98] ${
              rejected ? 'bg-uic-steel text-white shadow-sm hover:bg-uic-steel/90' : 'border border-black/10 bg-white text-uic-navy hover:bg-black/[0.03]'
            }`}
          >
            <X size={16} aria-hidden="true" />
            {rejected ? 'Rejected' : 'Reject'}
          </button>
          <button
            type="button"
            onClick={() => onDecide(null)}
            disabled={!decided}
            title={`Follow the ${ruleset.ruleset_name} toggle again`}
            className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-uic-steel/80 transition hover:bg-black/5 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
          >
            <RotateCcw size={15} aria-hidden="true" />
            Reset to ruleset
          </button>
        </div>
      </div>
    </div>
  )
  return sheet ? createPortal(dialog, document.body) : dialog
}

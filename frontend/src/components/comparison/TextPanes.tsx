import { Check, FileText, Sparkles, X } from 'lucide-react'
import { Fragment, memo, useCallback, useLayoutEffect, useRef, type CSSProperties, type KeyboardEvent, type Ref } from 'react'
import type { ChangeDecision, Decisions, Segment } from '../../lib/changes'
import type { Change, RulesetId, RulesetInfo } from '../../types/api'
import PaneFrame from './PaneFrame'
import { changeState, prefersReducedMotion, snippet, tint } from './utils'

type SelectHandler = (changeId: string) => void

/** Soft fade/blur when a change's text swaps (reveal toggled, accepted, rejected). */
function useSwapAnimation(version: string) {
  const ref = useRef<HTMLSpanElement | null>(null)
  const mounted = useRef(false)
  useLayoutEffect(() => {
    if (!mounted.current) {
      mounted.current = true
      return
    }
    const el = ref.current
    if (!el || typeof el.animate !== 'function' || prefersReducedMotion()) return
    el.animate(
      [{ opacity: 0.1, filter: 'blur(2px)' }, { opacity: 1, filter: 'blur(0)' }],
      { duration: 340, easing: 'cubic-bezier(0.2, 0.7, 0.3, 1)' },
    )
  }, [version])
  return ref
}

interface ChangeMarkProps {
  change: Change
  text: string
  applied: boolean
  decision: ChangeDecision | undefined
  color: string
  rulesetName: string
  selected: boolean
  highlights: boolean
  onSelect: SelectHandler
}

/** One change in the improved text: a highlighted, keyboard-focusable trigger for its explanation. */
const ChangeMark = memo(function ChangeMark({
  change, text, applied, decision, color, rulesetName, selected, highlights, onSelect,
}: ChangeMarkProps) {
  const ref = useSwapAnimation(`${applied}|${text}`)
  const state = changeState(applied, decision)
  const id = change.change_id

  if (!highlights || state === 'hidden') {
    return (
      <span ref={ref} data-anchor="improved" data-change-id={id}>
        {text}
      </span>
    )
  }

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(id)
    }
  }
  const decided = state === 'accepted' ? ', accepted' : state === 'rejected' ? ', rejected' : ''
  const label = text
    ? `“${snippet(text, 80)}”: ${rulesetName} change${decided}`
    : `Removed “${snippet(change.original_text, 80)}”: ${rulesetName} change${decided}`
  const style: CSSProperties =
    state === 'rejected'
      ? { border: `1.5px dashed ${color}`, backgroundColor: 'transparent' }
      : { backgroundColor: tint(color, '26'), borderBottom: `2px solid ${color}` }

  return (
    <span
      ref={ref}
      role="button"
      tabIndex={0}
      data-anchor="improved"
      data-change-trigger="mark"
      data-change-id={id}
      data-label={`${rulesetName}${state === 'accepted' ? ' · Accepted' : state === 'rejected' ? ' · Rejected' : ''}`}
      aria-label={label}
      aria-haspopup="dialog"
      aria-expanded={selected}
      onClick={() => onSelect(id)}
      onKeyDown={onKeyDown}
      style={style}
      className={`relative cursor-pointer rounded-[3px] box-decoration-clone px-px transition-[background-color,border-color,box-shadow] duration-300 hover:brightness-95 ${
        selected ? 'shadow-[0_0_0_2px_var(--color-uic-navy)]' : ''
      } after:pointer-events-none after:absolute after:bottom-full after:left-0 after:z-10 after:mb-1 after:rounded-md after:bg-uic-navy after:px-1.5 after:py-0.5 after:text-[11px] after:leading-4 after:font-medium after:whitespace-nowrap after:text-white after:opacity-0 after:shadow-sm after:transition-opacity after:content-[attr(data-label)] hover:after:opacity-100 focus-visible:after:opacity-100`}
    >
      {text || (
        <span
          aria-hidden="true"
          className="mx-px inline-block h-[1.05em] w-1.5 rounded-sm align-[-0.15em]"
          style={{ backgroundColor: tint(color, '99') }}
        />
      )}
      {(state === 'accepted' || state === 'rejected') && (
        <span
          aria-hidden="true"
          className="ml-0.5 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full align-[0.1em] text-white"
          style={{ backgroundColor: state === 'accepted' ? '#00966C' : '#6B7280' }}
        >
          {state === 'accepted' ? <Check size={9} strokeWidth={4} /> : <X size={9} strokeWidth={4} />}
        </span>
      )}
    </span>
  )
})

interface PaneTextProps {
  original: string
  segments: Segment[]
  decisions: Decisions
  rulesetById: Record<RulesetId, RulesetInfo>
  selectedChangeId: string | null
  highlights: boolean
  onSelect: SelectHandler
}

const ImprovedText = memo(function ImprovedText({
  segments, decisions, rulesetById, selectedChangeId, highlights, onSelect,
}: Omit<PaneTextProps, 'original'>) {
  return (
    <>
      {segments.map((s, i) =>
        s.kind === 'equal' ? (
          <Fragment key={`e${i}`}>{s.text}</Fragment>
        ) : (
          <ChangeMark
            key={s.change.change_id}
            change={s.change}
            text={s.text}
            applied={s.applied}
            decision={decisions[s.change.change_id]}
            color={rulesetById[s.change.ruleset].highlight_color}
            rulesetName={rulesetById[s.change.ruleset].ruleset_name}
            selected={selectedChangeId === s.change.change_id}
            highlights={highlights}
            onSelect={onSelect}
          />
        ),
      )}
    </>
  )
})

interface OriginalMarkProps {
  change: Change
  text: string
  removed: boolean
  color: string
  rulesetName: string
  onSelect: SelectHandler
}

/** A span of the original. When its change is applied it is struck through in the ruleset color. */
const OriginalMark = memo(function OriginalMark({ change, text, removed, color, rulesetName, onSelect }: OriginalMarkProps) {
  const ref = useSwapAnimation(String(removed))
  const id = change.change_id
  if (!removed) {
    return (
      <span ref={ref} data-anchor="original" data-change-id={id}>
        {text}
      </span>
    )
  }
  return (
    <del
      ref={ref as Ref<HTMLElement> as Ref<HTMLModElement>}
      data-anchor="original"
      data-change-id={id}
      title={`${rulesetName}: replaced with “${snippet(change.rewritten_text, 60) || '(removed)'}”`}
      onClick={() => onSelect(id)}
      className="cursor-pointer rounded-[3px] box-decoration-clone px-px text-uic-steel/70 line-through decoration-2 transition-colors duration-300"
      style={{ textDecorationColor: color, backgroundColor: tint(color, '14') }}
    >
      {text}
    </del>
  )
})

const OriginalText = memo(function OriginalText({
  original, segments, rulesetById, highlights, onSelect,
}: Omit<PaneTextProps, 'decisions' | 'selectedChangeId'>) {
  if (!highlights) return <>{original}</>
  return (
    <>
      {segments.map((s, i) => {
        if (s.kind === 'equal') return <Fragment key={`e${i}`}>{s.text}</Fragment>
        const c = s.change
        const span = original.slice(c.original_start, c.original_end)
        if (!span) return null
        return (
          <OriginalMark
            key={c.change_id}
            change={c}
            text={span}
            removed={s.applied}
            color={rulesetById[c.ruleset].highlight_color}
            rulesetName={rulesetById[c.ruleset].ruleset_name}
            onSelect={onSelect}
          />
        )
      })}
    </>
  )
})

export interface TextPanesProps extends PaneTextProps {
  mobileTab: 'original' | 'improved'
  originalWords: number
  improvedWords: number
  appliedCount: number
}

/** Side-by-side Original | Improved panes with proportional scroll sync (stacked tabs on narrow screens). */
function TextPanes({
  original, segments, decisions, rulesetById, selectedChangeId, highlights, onSelect,
  mobileTab, originalWords, improvedWords, appliedCount,
}: TextPanesProps) {
  const origRef = useRef<HTMLDivElement>(null)
  const implRef = useRef<HTMLDivElement>(null)
  const locked = useRef(false)

  const sync = useCallback((from: HTMLDivElement | null, to: HTMLDivElement | null) => {
    if (locked.current || !from || !to) return
    const fromMax = from.scrollHeight - from.clientHeight
    const toMax = to.scrollHeight - to.clientHeight
    if (fromMax <= 0 || toMax <= 0) return
    locked.current = true
    to.scrollTop = (from.scrollTop / fromMax) * toMax
    requestAnimationFrame(() => {
      locked.current = false
    })
  }, [])

  return (
    <div className="grid gap-3 @2xl:grid-cols-2">
      <PaneFrame
        label="Original"
        tone="original"
        icon={<FileText size={14} aria-hidden="true" />}
        meta={`${originalWords.toLocaleString()} words`}
        className={mobileTab === 'original' ? 'flex' : 'hidden @2xl:flex'}
        scrollRef={origRef}
        onScroll={() => sync(origRef.current, implRef.current)}
        focusable
      >
        <OriginalText original={original} segments={segments} rulesetById={rulesetById} highlights={highlights} onSelect={onSelect} />
      </PaneFrame>
      <PaneFrame
        label="Improved"
        tone="improved"
        icon={<Sparkles size={14} aria-hidden="true" />}
        meta={`${appliedCount} ${appliedCount === 1 ? 'change' : 'changes'} · ${improvedWords.toLocaleString()} words`}
        className={mobileTab === 'improved' ? 'flex' : 'hidden @2xl:flex'}
        scrollRef={implRef}
        onScroll={() => sync(implRef.current, origRef.current)}
        focusable={!highlights || appliedCount === 0}
      >
        <ImprovedText
          segments={segments}
          decisions={decisions}
          rulesetById={rulesetById}
          selectedChangeId={selectedChangeId}
          highlights={highlights}
          onSelect={onSelect}
        />
      </PaneFrame>
    </div>
  )
}

export default memo(TextPanes)

import { Highlighter, Info, RotateCcw } from 'lucide-react'
import { useCallback, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useRulesets } from '../context/RulesetContext'
import { useText } from '../context/TextContext'
import { useUI } from '../context/UIContext'
import { countWords, type ChangeDecision } from '../lib/changes'
import { DEFAULT_DEMO_SAMPLE } from '../data/demoSamples'
import type { RulesetId } from '../types/api'
import ChangeDetail from './comparison/ChangeDetail'
import ChangeList from './comparison/ChangeList'
import { EmptyState, LoadingState } from './comparison/ComparisonStates'
import RevealBar from './comparison/RevealBar'
import TextPanes from './comparison/TextPanes'
import { useComparisonData } from './comparison/useComparisonData'
import { changeState, findChangeTrigger } from './comparison/utils'

type MobileTab = 'original' | 'improved'

/**
 * Task 4.6 — side-by-side Original | Improved comparison with progressive reveal (SPEC Core
 * Innovation, FR-5, FR-6), interactive explanations (FR-9) and hybrid acceptance (FR-10).
 */
export default function ComparisonView() {
  const { text, setText, analysis, status, isStale, decisions, setDecision, resetDecisions } = useText()
  const {
    revealed, toggleReveal, revealNext, revealAll, revealNone,
    showHighlights, setShowHighlights, selectedChangeId, selectChange, notify,
  } = useUI()
  const { rulesetById, setAudience, setChannel } = useRulesets()
  const data = useComparisonData(analysis, revealed, decisions)
  const titleId = useId()

  const [mobileTab, setMobileTab] = useState<MobileTab>('improved')
  const [announcement, setAnnouncement] = useState({ message: '', n: 0 })
  const announce = useCallback((message: string) => setAnnouncement((a) => ({ message, n: a.n + 1 })), [])

  const sectionRef = useRef<HTMLElement>(null)
  const panesRef = useRef<HTMLDivElement>(null)
  /** What had focus when the popover opened, and for which change (focus goes back there on Esc). */
  const openerRef = useRef<{ el: HTMLElement | null; id: string | null }>({ el: null, id: null })
  const selectedRef = useRef(selectedChangeId)
  // Layout effect: runs before ChangeDetail moves focus into itself, so a change opened from
  // elsewhere (e.g. "Show suggested change" in the issues list) still records its opener.
  useLayoutEffect(() => {
    const prev = selectedRef.current
    selectedRef.current = selectedChangeId
    if (!selectedChangeId) openerRef.current = { el: null, id: null }
    else if (!prev && openerRef.current.id !== selectedChangeId) {
      openerRef.current = { el: document.activeElement instanceof HTMLElement ? document.activeElement : null, id: selectedChangeId }
    }
  }, [selectedChangeId])

  const name = useCallback((id: RulesetId) => rulesetById[id]?.ruleset_name ?? id, [rulesetById])

  // ---------------------------------------------------------------- change selection (FR-9)
  const closeDetail = useCallback(
    (returnFocus: boolean) => {
      const id = selectedRef.current
      selectChange(null)
      if (!returnFocus || !id) return
      const opener = openerRef.current
      openerRef.current = { el: null, id: null }
      const target =
        opener.el?.isConnected && opener.el !== document.body && opener.id === id
          ? opener.el
          : findChangeTrigger(sectionRef.current, id)
      target?.focus()
    },
    [selectChange],
  )

  const openChange = useCallback(
    (id: string) => {
      if (selectedRef.current === id) {
        selectChange(null)
        return
      }
      openerRef.current = { el: document.activeElement instanceof HTMLElement ? document.activeElement : null, id }
      selectChange(id)
    },
    [selectChange],
  )

  const stepChange = useCallback(
    (delta: -1 | 1) => {
      if (!data || !selectedChangeId) return
      const i = data.changeIndex.get(selectedChangeId)
      const next = i === undefined ? undefined : data.changes[i + delta]
      if (next) selectChange(next.change_id)
    },
    [data, selectedChangeId, selectChange],
  )

  const decide = useCallback(
    (decision: ChangeDecision | null) => {
      if (!selectedChangeId) return
      setDecision(selectedChangeId, decision)
      announce(decision === 'accepted' ? 'Change accepted' : decision === 'rejected' ? 'Change rejected — original wording kept' : 'Change now follows its ruleset')
    },
    [selectedChangeId, setDecision, announce],
  )

  // ---------------------------------------------------------------- progressive reveal (FR-5)
  const onToggle = useCallback(
    (id: RulesetId) => {
      const willShow = !revealed.has(id)
      toggleReveal(id)
      announce(`${name(id)} changes ${willShow ? 'shown' : 'hidden'}`)
    },
    [revealed, toggleReveal, announce, name],
  )
  const onRevealNext = useCallback(() => {
    if (!data) return
    const shown = data.available.filter((r) => revealed.has(r)).length
    const r = revealNext(data.available)
    if (r) announce(`${name(r)} changes shown. ${shown + 1} of ${data.available.length} rulesets applied.`)
  }, [data, revealed, revealNext, announce, name])
  const onShowAll = useCallback(() => {
    revealAll()
    announce('All changes shown')
  }, [revealAll, announce])
  const onShowNone = useCallback(() => {
    revealNone()
    announce('Showing your original text')
  }, [revealNone, announce])

  const onResetDecisions = useCallback(() => {
    resetDecisions()
    announce('Your accept and reject choices were cleared')
  }, [resetDecisions, announce])

  const onToggleHighlights = useCallback(() => {
    setShowHighlights(!showHighlights)
    announce(showHighlights ? 'Highlights hidden' : 'Highlights shown')
  }, [showHighlights, setShowHighlights, announce])

  const onTrySample = useCallback(() => {
    setText(DEFAULT_DEMO_SAMPLE.text)
    setAudience(DEFAULT_DEMO_SAMPLE.audience)
    setChannel(DEFAULT_DEMO_SAMPLE.channel)
    notify(`Loaded “${DEFAULT_DEMO_SAMPLE.title}” — click Analyze to see suggestions`, 'info')
  }, [setText, setAudience, setChannel, notify])

  const words = useMemo(() => {
    if (!data || !analysis) return { original: 0, improved: 0 }
    return {
      original: countWords(analysis.original),
      improved: countWords(data.segments.map((s) => s.text).join('')),
    }
  }, [analysis, data])

  const loading = status === 'loading'
  const selected = data && selectedChangeId !== null ? data.changes[data.changeIndex.get(selectedChangeId) ?? -1] : undefined

  const header = (
    <h2 id={titleId} className="text-base font-semibold text-uic-navy">
      Original <span aria-hidden="true">→</span>
      <span className="sr-only">to</span> Improved
    </h2>
  )

  return (
    <section
      ref={sectionRef}
      aria-labelledby={titleId}
      aria-busy={loading || undefined}
      className="@container rounded-2xl border border-black/5 bg-white p-5 shadow-sm sm:p-6"
    >
      <p className="sr-only" role="status" aria-live="polite">
        {announcement.message}
        {announcement.n % 2 ? '​' : ''}
      </p>

      {loading ? (
        <>
          {header}
          <LoadingState text={text} />
        </>
      ) : !analysis || !data ? (
        <>
          {header}
          <EmptyState onTrySample={text.trim() ? undefined : onTrySample} />
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              {header}
              <p className="mt-0.5 text-xs text-uic-steel/70 tabular-nums">
                {data.appliedCount} of {data.changes.length} changes applied
                {data.decisionCount > 0 && ` · ${data.decisionCount} reviewed by you`}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {data.decisionCount > 0 && (
                <button
                  type="button"
                  onClick={onResetDecisions}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-uic-steel/80 transition hover:bg-black/5 hover:text-uic-navy"
                >
                  <RotateCcw size={15} aria-hidden="true" />
                  Reset decisions
                </button>
              )}
              <button
                type="button"
                aria-pressed={showHighlights}
                onClick={onToggleHighlights}
                title="Show or hide the colored highlights. Select a highlight to see why it changed."
                className="inline-flex min-h-10 items-center gap-2 rounded-xl py-2 pr-2.5 pl-3 text-sm font-medium text-uic-navy transition hover:bg-black/[0.04]"
              >
                <Highlighter size={16} aria-hidden="true" />
                Highlights
                <span
                  aria-hidden="true"
                  className={`relative ml-0.5 inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200 ${
                    showHighlights ? 'bg-uic-navy' : 'bg-black/15'
                  }`}
                >
                  <span
                    className={`absolute h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      showHighlights ? 'translate-x-[18px]' : 'translate-x-0.5'
                    }`}
                  />
                </span>
              </button>
            </div>
          </div>

          {isStale && (
            <div
              role="status"
              className="mt-4 flex items-start gap-2.5 rounded-xl bg-uic-beach px-3.5 py-2.5 text-sm text-uic-steel"
            >
              <Info size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-[#B45309]" />
              <span>Your draft or settings changed — re-run Analyze to refresh.</span>
            </div>
          )}

          <RevealBar
            rulesets={data.rulesets}
            available={data.available}
            revealed={revealed}
            rulesetById={rulesetById}
            onToggle={onToggle}
            onRevealNext={onRevealNext}
            onShowAll={onShowAll}
            onShowNone={onShowNone}
          />

          <div className="mt-4 grid gap-4">
            <div ref={panesRef} className="relative min-w-0">
              <div role="group" aria-label="Choose which version to read" className="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-black/[0.04] p-1 @2xl:hidden">
                {(['original', 'improved'] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    aria-pressed={mobileTab === tab}
                    onClick={() => setMobileTab(tab)}
                    className={`min-h-10 rounded-lg px-3 py-2 text-sm font-medium transition ${
                      mobileTab === tab ? 'bg-white text-uic-navy shadow-sm' : 'text-uic-steel/80 hover:text-uic-navy'
                    }`}
                  >
                    {tab === 'original' ? 'Original' : 'Improved'}
                  </button>
                ))}
              </div>

              <TextPanes
                original={analysis.original}
                segments={data.segments}
                decisions={decisions}
                rulesetById={rulesetById}
                selectedChangeId={selectedChangeId}
                highlights={showHighlights}
                onSelect={openChange}
                mobileTab={mobileTab}
                originalWords={words.original}
                improvedWords={words.improved}
                appliedCount={data.appliedCount}
              />

              {selected && (
                <ChangeDetail
                  key="detail"
                  change={selected}
                  index={data.changeIndex.get(selected.change_id) ?? 0}
                  total={data.changes.length}
                  state={changeState(data.appliedIds.has(selected.change_id), decisions[selected.change_id])}
                  ruleset={rulesetById[selected.ruleset]}
                  issues={selected.issue_ids.flatMap((id) => data.issuesById.get(id) ?? [])}
                  containerRef={panesRef}
                  onClose={closeDetail}
                  onDecide={decide}
                  onStep={stepChange}
                />
              )}
            </div>

            {data.changes.length > 0 && (
              <ChangeList
                changes={data.changes}
                rulesets={data.rulesets}
                rulesetById={rulesetById}
                appliedIds={data.appliedIds}
                decisions={decisions}
                selectedChangeId={selectedChangeId}
                onSelect={openChange}
              />
            )}
          </div>
        </>
      )}
    </section>
  )
}

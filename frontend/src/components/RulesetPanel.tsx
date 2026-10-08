import { AlertTriangle, CheckCircle2, Globe, Loader2, Mail, MessageCircle, RotateCcw, Wand2, X } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { CHANNELS } from '../config/rulesets'
import { useRulesets } from '../context/RulesetContext'
import { useText } from '../context/TextContext'
import type { Channel } from '../types/api'
import RulesetToggle from './input/RulesetToggle'
import SegmentedControl, { type SegmentOption } from './input/SegmentedControl'
import { useAnalyzeGate } from './input/useAnalyzeGate'
import { cx, plural } from './input/utils'

const CHANNEL_ICONS: Record<Channel, ReactNode> = {
  Email: <Mail size={15} />,
  Website: <Globe size={15} />,
  'Social Media': <MessageCircle size={15} />,
}

const linkBtn =
  'rounded px-1 py-0.5 text-xs font-medium text-uic-navy/80 underline-offset-2 transition duration-150 hover:text-uic-navy hover:underline disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:no-underline'

/**
 * Task 4.5 — analysis settings: audience, channel and which of the 5 rulesets to check, plus the
 * primary Analyze action with loading / cancel / disabled-reason / error + retry states.
 * Unusual combinations are allowed with one gentle warning (SPEC: "warn but allow").
 */
export default function RulesetPanel() {
  const { audience, setAudience, channel, setChannel, rulesets, selectedRulesets, toggleRuleset, setSelectedRulesets, audiences } =
    useRulesets()
  const { status, error, runAnalysis, cancelAnalysis, analysis, isStale } = useText()
  const { reason, canAnalyze } = useAnalyzeGate()
  const uid = useId()
  const titleId = `${uid}-title`
  const reasonId = `${uid}-reason`
  const checksId = `${uid}-checks`

  const loading = status === 'loading'
  const allIds = rulesets.map((r) => r.ruleset_id)
  const allOn = allIds.every((id) => selectedRulesets.includes(id))
  const noneOn = selectedRulesets.length === 0
  const audienceInfo = audiences.find((a) => a.id === audience)

  const audienceOptions: SegmentOption<typeof audience>[] = audiences.map((a) => ({
    value: a.id,
    label: a.label,
    description: `${a.description}. Target reading level: grade ${a.reading_level_target}.`,
  }))
  const channelOptions: SegmentOption<Channel>[] = CHANNELS.map((c) => ({
    value: c.id,
    label: c.id === 'Social Media' ? 'Social' : c.label,
    description: `${c.label}: ${c.description}`,
    icon: CHANNEL_ICONS[c.id],
  }))

  // At most one gentle, non-blocking warning (blocking reasons live by the button).
  let warning: ReactNode = null
  if (!noneOn && !selectedRulesets.includes('reading_level') && audienceInfo) {
    warning = `Reading Level is off — ${audienceInfo.label} should read at about grade ${audienceInfo.reading_level_target}.`
  } else if (!noneOn && !selectedRulesets.includes('accessibility')) {
    warning = 'Accessibility is off — UIC communications should meet WCAG 2.1 AA.'
  } else if (!noneOn && channel === 'Social Media' && !selectedRulesets.includes('audience_tone')) {
    warning = 'Audience Tone is off — tone matters most in short social posts.'
  }

  const upToDate = status === 'success' && !!analysis && !isStale
  const buttonLabel = loading ? 'Analyzing…' : analysis && isStale ? 'Re-analyze draft' : upToDate ? 'Analyze again' : 'Analyze draft'
  const disabled = !canAnalyze

  const onAnalyze = () => {
    if (disabled) return
    void runAnalysis()
  }

  return (
    <section aria-labelledby={titleId} className="rounded-2xl border border-black/5 bg-white p-4 shadow-sm sm:p-5">
      <h2 id={titleId} className="text-base font-semibold text-uic-navy">
        Settings
      </h2>

      <div className="mt-3 space-y-2">
        <SegmentedControl legend="Audience" value={audience} onChange={setAudience} options={audienceOptions} />
        <SegmentedControl legend="Channel" value={channel} onChange={setChannel} options={channelOptions} />
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span id={checksId} className="text-[13px] text-uic-steel/70">
            Checks
          </span>
          <div className="flex items-center text-uic-steel/30">
            <button type="button" className={linkBtn} disabled={allOn} onClick={() => setSelectedRulesets(allIds)}>
              Select all
            </button>
            <span aria-hidden="true">·</span>
            <button type="button" className={linkBtn} disabled={noneOn} onClick={() => setSelectedRulesets([])}>
              None
            </button>
          </div>
        </div>
        <div role="group" aria-labelledby={checksId} className="flex flex-wrap gap-1.5">
          {rulesets.map((r) => (
            <RulesetToggle
              key={r.ruleset_id}
              ruleset={r}
              checked={selectedRulesets.includes(r.ruleset_id)}
              onToggle={() => toggleRuleset(r.ruleset_id)}
            />
          ))}
        </div>
        {warning && (
          <p data-testid="settings-warning" className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-[#8A4B0B]">
            <AlertTriangle size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
            <span>{warning}</span>
          </p>
        )}
      </div>

      <div className="mt-5">
        {status === 'error' && error && (
          <div
            role="alert"
            className="mb-3 flex items-center gap-3 rounded-xl bg-uic-red/[0.05] px-3 py-2.5 transition duration-200 ease-out starting:opacity-0"
          >
            <AlertTriangle size={16} aria-hidden="true" className="shrink-0 text-uic-red" />
            <p className="min-w-0 flex-1 text-[13px] leading-snug text-uic-steel/90">
              <span className="font-semibold text-[#A3001F]">We couldn’t finish the analysis.</span> {error.message}
            </p>
            <button
              type="button"
              onClick={() => void runAnalysis()}
              disabled={!canAnalyze}
              className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-uic-navy transition duration-150 hover:bg-black/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw size={14} aria-hidden="true" />
              Retry
            </button>
          </div>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onAnalyze}
            aria-disabled={disabled || undefined}
            aria-describedby={reason && !loading ? reasonId : undefined}
            aria-keyshortcuts="Meta+Enter Control+Enter"
            className={cx(
              'inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-uic-navy px-5 text-[15px] font-semibold text-white shadow-sm transition duration-150 ease-out',
              disabled ? cx('cursor-not-allowed', loading ? 'opacity-90' : 'opacity-50') : 'hover:bg-uic-navy/90 active:scale-[0.99]',
            )}
          >
            {loading ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : <Wand2 size={18} aria-hidden="true" />}
            {buttonLabel}
          </button>
          {loading && (
            <button
              type="button"
              onClick={cancelAnalysis}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-black/10 bg-white px-3.5 text-sm font-medium text-uic-steel transition duration-150 hover:bg-black/[0.03] active:scale-[0.97] starting:opacity-0"
            >
              <X size={16} aria-hidden="true" />
              Cancel
            </button>
          )}
        </div>

        <div className="mt-2 min-h-5 text-center text-xs" aria-live="polite">
          {reason && !loading ? (
            <p id={reasonId} className="text-uic-steel/75">
              {reason}
            </p>
          ) : loading ? (
            <p className="text-uic-steel/70">Checking your draft…</p>
          ) : upToDate ? (
            <p className="flex items-center justify-center gap-1.5 font-medium text-[#007A58]">
              <CheckCircle2 size={13} aria-hidden="true" />
              Analysis complete · {plural(analysis?.scores.total_issues ?? 0, 'issue')} found
            </p>
          ) : analysis && isStale ? (
            <p className="text-[#8A4B0B]">Draft or settings changed since the last analysis.</p>
          ) : null}
        </div>
      </div>
    </section>
  )
}

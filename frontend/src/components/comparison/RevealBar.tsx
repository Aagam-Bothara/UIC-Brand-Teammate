import { Check, Eye, EyeOff, RotateCcw, StepForward } from 'lucide-react'
import { RULESET_ORDER } from '../../config/rulesets'
import type { RulesetId, RulesetInfo } from '../../types/api'
import type { RulesetSummary } from './useComparisonData'
import { tint } from './utils'

interface RevealBarProps {
  rulesets: RulesetSummary[]
  available: RulesetId[]
  revealed: ReadonlySet<RulesetId>
  rulesetById: Record<RulesetId, RulesetInfo>
  onToggle: (id: RulesetId) => void
  onRevealNext: () => void
  onShowAll: () => void
  onShowNone: () => void
}

const quietBtn =
  'inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-uic-navy transition hover:bg-black/[0.04] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent'

/**
 * Progressive reveal (SPEC Core Innovation / FR-5): one toggle per ruleset plus a step-by-step
 * "Reveal next" control for demos. Toggling never re-generates; it only changes which pre-generated
 * layered edits are visible.
 */
export default function RevealBar({
  rulesets, available, revealed, rulesetById, onToggle, onRevealNext, onShowAll, onShowNone,
}: RevealBarProps) {
  const shown = available.filter((r) => revealed.has(r))
  const next = RULESET_ORDER.find((r) => available.includes(r) && !revealed.has(r)) ?? null
  const allShown = available.length > 0 && shown.length === available.length
  const noneShown = shown.length === 0

  return (
    <div className="mt-4">
      <div role="group" aria-label="Reveal changes by ruleset" className="flex flex-wrap gap-2">
        {rulesets.map(({ id, total }) => {
          const info = rulesetById[id]
          const color = info.highlight_color
          const on = revealed.has(id)
          if (total === 0) {
            return (
              <button
                key={id}
                type="button"
                disabled
                title={`${info.ruleset_name}: no changes needed`}
                className="inline-flex min-h-10 cursor-not-allowed items-center gap-2 rounded-full border border-dashed border-black/15 px-3 py-1.5 text-sm text-uic-steel/70"
              >
                <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full opacity-50" style={{ backgroundColor: color }} />
                <span className="font-medium">{info.ruleset_name}</span>
                <span className="sr-only">: No changes</span>
              </button>
            )
          }
          return (
            <button
              key={id}
              type="button"
              aria-pressed={on}
              aria-label={`${info.ruleset_name}, ${total} ${total === 1 ? 'change' : 'changes'}`}
              title={info.description}
              onClick={() => onToggle(id)}
              className={`group inline-flex min-h-10 items-center gap-2 rounded-full border py-1.5 pr-2 pl-2.5 text-sm font-medium transition duration-200 active:scale-[0.97] ${
                on ? 'text-uic-navy' : 'border-black/10 bg-white text-uic-steel/80 hover:bg-black/[0.03]'
              }`}
              style={on ? { backgroundColor: tint(color, '1F'), borderColor: tint(color, '80') } : undefined}
            >
              <span
                aria-hidden="true"
                className="flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 transition-colors duration-200"
                style={{ borderColor: color, backgroundColor: on ? color : 'transparent' }}
              >
                <Check size={11} strokeWidth={3.5} className={`text-white transition-opacity ${on ? 'opacity-100' : 'opacity-0'}`} />
              </span>
              {info.ruleset_name}
              <span
                aria-hidden="true"
                className={`min-w-6 rounded-full px-1.5 py-0.5 text-center text-xs tabular-nums transition-colors ${on ? 'bg-white/80' : 'bg-black/5'}`}
              >
                {total}
              </span>
            </button>
          )
        })}
      </div>

      {available.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-2">
          {next ? (
            <button
              type="button"
              onClick={onRevealNext}
              aria-label={`Reveal next: ${rulesetById[next].ruleset_name}`}
              className="mr-1 inline-flex min-h-10 items-center gap-2 rounded-xl bg-uic-navy px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-uic-navy/90 active:scale-[0.98]"
            >
              <StepForward size={16} aria-hidden="true" />
              <span>
                Reveal next
                <span className="font-normal text-white/80">
                  {' · '}
                  {rulesetById[next].ruleset_name}
                </span>
              </span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onShowNone}
              title="Hide every change, then reveal them one ruleset at a time"
              className="mr-1 inline-flex min-h-10 items-center gap-2 rounded-xl bg-uic-navy px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-uic-navy/90 active:scale-[0.98]"
            >
              <RotateCcw size={16} aria-hidden="true" />
              Replay step by step
            </button>
          )}
          <button type="button" onClick={onShowAll} disabled={allShown} className={quietBtn}>
            <Eye size={16} aria-hidden="true" />
            Show all
          </button>
          <button type="button" onClick={onShowNone} disabled={noneShown} className={quietBtn}>
            <EyeOff size={16} aria-hidden="true" />
            Original only
          </button>
          <p className="ml-auto flex items-center gap-2 text-xs text-uic-steel/70 tabular-nums">
            <span aria-hidden="true" className="flex gap-0.5">
              {available.map((id) => (
                <span
                  key={id}
                  className="h-1 w-3 rounded-full transition-colors duration-300"
                  style={{ backgroundColor: revealed.has(id) ? rulesetById[id].highlight_color : 'rgb(0 0 0 / 0.1)' }}
                />
              ))}
            </span>
            <span aria-hidden="true">
              {shown.length}/{available.length}
            </span>
            <span className="sr-only">
              {shown.length} of {available.length} rulesets applied
            </span>
          </p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-uic-steel/80">No changes needed for the selected rulesets.</p>
      )}
    </div>
  )
}

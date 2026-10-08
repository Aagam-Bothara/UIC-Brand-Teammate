import { ArrowRight, Check, ChevronDown, ListChecks, X } from 'lucide-react'
import { memo, useId, useState } from 'react'
import type { Decisions } from '../../lib/changes'
import type { Change, RulesetId, RulesetInfo } from '../../types/api'
import type { RulesetSummary } from './useComparisonData'
import { STATE_LABEL, changeState, snippet, tint, type ChangeState } from './utils'

function StateIcon({ state, color }: { state: ChangeState; color: string }) {
  const base = 'mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-white'
  if (state === 'accepted')
    return (
      <span aria-hidden="true" className={base} style={{ backgroundColor: '#00966C' }}>
        <Check size={11} strokeWidth={3.5} />
      </span>
    )
  if (state === 'rejected')
    return (
      <span aria-hidden="true" className={`${base} border-[1.5px] border-dashed border-uic-steel/50 text-uic-steel/70`}>
        <X size={10} strokeWidth={3.5} />
      </span>
    )
  if (state === 'applied')
    return (
      <span aria-hidden="true" className={base} style={{ backgroundColor: color }}>
        <Check size={11} strokeWidth={3.5} />
      </span>
    )
  return <span aria-hidden="true" className={`${base} border-2`} style={{ borderColor: tint(color, '99') }} />
}

function EditSummary({ change }: { change: Change }) {
  const before = snippet(change.original_text, 48)
  const after = snippet(change.rewritten_text, 48)
  return (
    <span className="block text-[13px] leading-snug break-words">
      {before ? (
        <span className="text-uic-steel/70 line-through decoration-black/30">{before}</span>
      ) : (
        <span className="text-uic-steel/70 italic">Add</span>
      )}
      <ArrowRight size={12} aria-hidden="true" className="mx-1 inline align-[-1px] text-uic-steel/50" />
      <span className="sr-only"> becomes </span>
      {after ? <span className="font-medium text-uic-navy">{after}</span> : <span className="text-uic-steel/70 italic">remove</span>}
    </span>
  )
}

interface ChangeListProps {
  changes: Change[]
  rulesets: RulesetSummary[]
  rulesetById: Record<RulesetId, RulesetInfo>
  appliedIds: ReadonlySet<string>
  decisions: Decisions
  selectedChangeId: string | null
  onSelect: (id: string) => void
}

/** "Sidebar annotations": every change grouped by ruleset with its state; click to open it. */
function ChangeList({ changes, rulesets, rulesetById, appliedIds, decisions, selectedChangeId, onSelect }: ChangeListProps) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const groups = rulesets
    .filter((r) => r.total > 0)
    .map((r) => ({ ...r, items: changes.filter((c) => c.ruleset === r.id) }))

  return (
    <aside aria-label="All changes" className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-black/5 bg-white">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 w-full items-center gap-2 px-4 py-2.5 text-left transition hover:bg-black/[0.02]"
      >
        <ListChecks size={16} aria-hidden="true" className="text-uic-navy" />
        <span className="flex-1 text-sm font-semibold text-uic-navy">All changes</span>
        <span className="rounded-full bg-black/5 px-2 py-0.5 text-xs font-medium text-uic-steel/80 tabular-nums">{changes.length}</span>
        <ChevronDown size={16} aria-hidden="true" className={`text-uic-steel/60 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      <div id={panelId} hidden={!open} className="max-h-[min(65vh,36rem)] overflow-y-auto overscroll-contain border-t border-black/5 p-2 @3xl:columns-2 @3xl:gap-4">
        {groups.length === 0 && <p className="px-2 py-3 text-sm text-uic-steel/70">No changes suggested.</p>}
        {groups.map((g) => {
          const info = rulesetById[g.id]
          return (
            <section key={g.id} aria-label={`${info.ruleset_name} changes`} className="break-inside-avoid pb-1">
              <h4 className="flex items-center gap-2 px-2 pt-2 pb-1 text-xs font-medium tracking-wide text-uic-steel/70 uppercase">
                <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ backgroundColor: info.highlight_color }} />
                <span className="flex-1">{info.ruleset_name}</span>
                <span className="font-normal normal-case tabular-nums">
                  {g.applied}/{g.total} applied
                </span>
              </h4>
              <ul>
                {g.items.map((c) => {
                  const state = changeState(appliedIds.has(c.change_id), decisions[c.change_id])
                  const selected = c.change_id === selectedChangeId
                  return (
                    <li key={c.change_id}>
                      <button
                        type="button"
                        data-change-trigger="list"
                        data-change-id={c.change_id}
                        aria-current={selected || undefined}
                        onClick={() => onSelect(c.change_id)}
                        className={`flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition ${
                          selected ? 'bg-uic-navy/[0.06] ring-1 ring-uic-navy/20' : 'hover:bg-black/[0.03]'
                        }`}
                      >
                        <StateIcon state={state} color={info.highlight_color} />
                        <span className="min-w-0 flex-1">
                          <EditSummary change={c} />
                          <span className={`mt-0.5 block text-[11px] ${state === 'accepted' ? 'font-medium text-[#00785A]' : 'text-uic-steel/70'}`}>
                            {STATE_LABEL[state]}
                          </span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          )
        })}
      </div>
    </aside>
  )
}

export default memo(ChangeList)

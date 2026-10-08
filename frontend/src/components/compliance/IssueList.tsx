import { BookOpen, CircleCheck, ChevronDown, ExternalLink, MousePointerClick, PartyPopper } from 'lucide-react'
import { useId, useMemo, useState, type MouseEvent } from 'react'
import { RULESET_ORDER } from '../../config/rulesets'
import { useRulesets } from '../../context/RulesetContext'
import { useText } from '../../context/TextContext'
import { useUI } from '../../context/UIContext'
import { isChangeApplied, normalizeChanges } from '../../lib/changes'
import type { Change, Issue, RulesetId, Severity } from '../../types/api'
import { SEVERITIES, SEVERITY_META, isDocumentIssue, withAlpha } from './meta'

type Filter = 'all' | Severity

interface IssueListProps {
  openIssues: Issue[]
  resolvedIssues: Issue[]
  changes: Change[]
  /** The analysed original text (to normalize changes the same way the comparison view does). */
  original: string
}

const bySeverity = (a: Issue, b: Issue) => SEVERITY_META[a.severity].rank - SEVERITY_META[b.severity].rank || a.start - b.start

/** FR-8 issue report: open issues grouped by ruleset, severity filter, collapsed "Resolved" section. */
export default function IssueList({ openIssues, resolvedIssues, changes, original }: IssueListProps) {
  const { rulesetById } = useRulesets()
  const { selectChange, selectedChangeId, revealed } = useUI()
  const { decisions } = useText()
  const [filter, setFilter] = useState<Filter>('all')
  const [collapsed, setCollapsed] = useState<ReadonlySet<RulesetId>>(new Set())
  const [showResolved, setShowResolved] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const baseId = useId()

  // An issue can be fixed by several changes. Point at the first one that isn't applied yet (the
  // one still needed), else the first. Same normalized changes the comparison view renders.
  const changeFor = useMemo(() => {
    const map = new Map<string, Change[]>()
    for (const c of normalizeChanges(original, changes)) for (const id of c.issue_ids) map.set(id, [...(map.get(id) ?? []), c])
    return (issue: Issue) => {
      if (isDocumentIssue(issue)) return undefined
      const list = map.get(issue.issue_id)
      return list?.find((c) => !isChangeApplied(c, revealed, decisions)) ?? list?.[0]
    }
  }, [original, changes, revealed, decisions])

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: openIssues.length, high: 0, medium: 0, low: 0 }
    for (const i of openIssues) c[i.severity]++
    return c
  }, [openIssues])

  const groups = useMemo(() => {
    const visible = filter === 'all' ? openIssues : openIssues.filter((i) => i.severity === filter)
    return RULESET_ORDER.map((id) => ({ id, issues: visible.filter((i) => i.ruleset === id).sort(bySeverity) })).filter((g) => g.issues.length > 0)
  }, [openIssues, filter])

  const toggleGroup = (id: RulesetId) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const filterLabel: Record<Filter, string> = { all: 'All', high: 'High', medium: 'Medium', low: 'Low' }

  return (
    <div>
      <h3>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={`${baseId}-issues`}
          onClick={() => setExpanded((v) => !v)}
          className="-mx-2 flex min-h-10 w-[calc(100%+1rem)] items-center gap-2 rounded-xl px-2 py-2 text-left transition duration-150 hover:bg-black/[0.03]"
        >
          <span className="flex-1 text-sm font-semibold text-uic-navy">
            Issues <span className="font-normal text-uic-steel/70 tabular-nums">({openIssues.length})</span>
            {resolvedIssues.length > 0 && (
              <span className="ml-2 text-xs font-normal text-uic-steel/70 tabular-nums">{resolvedIssues.length} resolved</span>
            )}
          </span>
          <ChevronDown size={16} aria-hidden="true" className={`text-uic-steel/60 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`} />
        </button>
      </h3>
      <div id={`${baseId}-issues`} hidden={!expanded}>
        {expanded && (
          <>
            <div className="mt-2 flex flex-wrap items-center justify-end gap-3">
              {openIssues.length > 0 && (
                <div role="group" aria-label="Filter issues by severity" className="inline-flex rounded-xl bg-black/[0.04] p-1">
                  {(['all', ...SEVERITIES] as Filter[]).map((f) => (
                    <button
                      key={f}
                      type="button"
                      aria-pressed={filter === f}
                      onClick={() => setFilter(f)}
                      className={`min-h-8 rounded-lg px-2.5 text-xs font-medium transition duration-150 ${
                        filter === f ? 'bg-white text-uic-navy shadow-sm' : 'text-uic-steel/70 hover:text-uic-navy'
                      }`}
                    >
                      {filterLabel[f]} <span className="tabular-nums">{counts[f]}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {openIssues.length === 0 ? (
              <div className="mt-4 flex items-center gap-3 rounded-xl border border-dashed border-black/10 p-4 text-sm text-uic-steel/80">
                <PartyPopper size={18} className="shrink-0 text-uic-green" aria-hidden="true" />
                No open issues. Everything flagged in your draft is addressed by the changes you’ve kept.
              </div>
            ) : groups.length === 0 ? (
              <p className="mt-4 rounded-xl border border-dashed border-black/10 p-4 text-sm text-uic-steel/80">
                No {filter}-severity issues left.{' '}
                <button type="button" className="font-medium text-uic-navy underline underline-offset-2" onClick={() => setFilter('all')}>
                  Show all issues
                </button>
              </p>
            ) : (
              <ul className="mt-4 space-y-3">
                {groups.map((g) => {
                  const info = rulesetById[g.id]
                  const open = !collapsed.has(g.id)
                  const panelId = `${baseId}-${g.id}`
                  return (
                    <li key={g.id} className="rounded-xl border border-black/5">
                      <h4>
                        <button
                          type="button"
                          aria-expanded={open}
                          aria-controls={panelId}
                          onClick={() => toggleGroup(g.id)}
                          className="flex min-h-10 w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left transition duration-150 hover:bg-black/[0.03]"
                        >
                          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: info.highlight_color }} aria-hidden="true" />
                          <span className="flex-1 text-sm font-semibold text-uic-navy">{info.ruleset_name}</span>
                          <span className="rounded-full bg-black/[0.05] px-2.5 py-0.5 text-xs font-medium tabular-nums text-uic-steel">
                            {g.issues.length} <span className="sr-only">{g.issues.length === 1 ? 'issue' : 'issues'}</span>
                          </span>
                          <ChevronDown size={16} aria-hidden="true" className={`text-uic-steel/60 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
                        </button>
                      </h4>
                      {open && (
                        <ul id={panelId} className="space-y-2 px-3 pb-3">
                          {g.issues.map((issue) => (
                            <IssueItem
                              key={issue.issue_id}
                              issue={issue}
                              color={info.highlight_color}
                              change={changeFor(issue)}
                              selected={!!selectedChangeId && changeFor(issue)?.change_id === selectedChangeId}
                              onSelect={selectChange}
                            />
                          ))}
                        </ul>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}

            {resolvedIssues.length > 0 && (
              <div className="mt-4 rounded-xl border border-black/5">
                <button
                  type="button"
                  aria-expanded={showResolved}
                  aria-controls={`${baseId}-resolved`}
                  onClick={() => setShowResolved((v) => !v)}
                  className="flex min-h-10 w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left transition duration-150 hover:bg-black/[0.03]"
                >
                  <CircleCheck size={16} className="shrink-0 text-uic-green" aria-hidden="true" />
                  <span className="flex-1 text-sm font-semibold text-uic-navy">Resolved ({resolvedIssues.length})</span>
                  <ChevronDown size={16} aria-hidden="true" className={`text-uic-steel/60 transition-transform duration-200 ${showResolved ? 'rotate-180' : ''}`} />
                </button>
                {showResolved && (
                  <ul id={`${baseId}-resolved`} className="divide-y divide-black/5 px-3 pb-2">
                    {[...resolvedIssues].sort((a, b) => RULESET_ORDER.indexOf(a.ruleset) - RULESET_ORDER.indexOf(b.ruleset) || a.start - b.start).map((issue) => {
                      const change = changeFor(issue)
                      const info = rulesetById[issue.ruleset]
                      return (
                        <li key={issue.issue_id} className="flex items-start gap-2.5 py-2.5">
                          <CircleCheck size={16} className="mt-0.5 shrink-0 text-uic-green" aria-label="Resolved" />
                          <div className="min-w-0 flex-1 text-sm">
                            <p className="text-uic-steel">
                              <span className="mr-1.5 inline-flex items-center gap-1 text-xs font-medium text-uic-steel/70">
                                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: info.highlight_color }} aria-hidden="true" />
                                {info.ruleset_name}
                              </span>
                              {issue.message}
                            </p>
                            {change && (
                              <p className="mt-0.5 break-words text-xs text-uic-steel/70">
                                <del className="decoration-uic-steel/40">{change.original_text || '(nothing)'}</del>
                                <span aria-hidden="true"> → </span>
                                <span className="sr-only"> changed to </span>
                                <ins className="no-underline font-medium text-uic-steel">{change.rewritten_text || '(removed)'}</ins>
                              </p>
                            )}
                          </div>
                          {change && (
                            <button
                              type="button"
                              onClick={() => selectChange(change.change_id)}
                              className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-uic-navy hover:bg-black/[0.04]"
                            >
                              View<span className="sr-only"> change: {issue.message}</span>
                            </button>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

interface IssueItemProps {
  issue: Issue
  color: string
  change: Change | undefined
  selected: boolean
  onSelect: (id: string) => void
}

function IssueItem({ issue, color, change, selected, onSelect }: IssueItemProps) {
  const sev = SEVERITY_META[issue.severity]
  const docLevel = isDocumentIssue(issue)
  const select = change ? () => onSelect(change.change_id) : undefined
  const onCardClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!select || (e.target as HTMLElement).closest('a, button')) return
    select()
  }

  return (
    <li>
      <div
        onClick={onCardClick}
        className={`rounded-xl border bg-white p-3 transition duration-150 ${
          select ? 'cursor-pointer hover:border-black/15 hover:shadow-sm' : ''
        } ${selected ? 'border-uic-navy/40 ring-2 ring-uic-navy/15' : 'border-black/5'}`}
      >
        <div className="flex items-start gap-2">
          <span className="mt-px shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium" style={{ backgroundColor: sev.bg, color: sev.text }}>
            {sev.label}
            <span className="sr-only"> severity</span>
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium leading-snug text-uic-steel">{issue.message}</p>
            {issue.rule_name && <p className="mt-0.5 text-xs text-uic-steel/70">{issue.rule_name}</p>}
          </div>
        </div>

        {docLevel ? (
          <p className="mt-2 text-xs text-uic-steel/70">Applies to the whole draft</p>
        ) : (
          issue.excerpt && (
            <blockquote
              className="mt-2 break-words rounded-r-lg border-l-2 py-1 pl-3 pr-2 text-sm text-uic-steel/90"
              style={{ borderColor: color, backgroundColor: withAlpha(color, 0.08) }}
            >
              “{issue.excerpt}”
            </blockquote>
          )
        )}

        {issue.suggestion && (
          <p className="mt-2 text-sm leading-relaxed text-uic-steel">
            <span className="font-medium text-uic-navy">Suggestion: </span>
            {issue.suggestion}
          </p>
        )}

        {(select || issue.guideline_url) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
            {select && (
              <button
                type="button"
                onClick={select}
                aria-pressed={selected}
                className="inline-flex min-h-8 items-center gap-1.5 rounded-lg text-xs font-medium text-uic-navy underline-offset-2 hover:underline"
              >
                <MousePointerClick size={14} aria-hidden="true" />
                Show suggested change<span className="sr-only">: {issue.message}</span>
              </button>
            )}
            {issue.guideline_url && (
              <a
                href={issue.guideline_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-8 items-center gap-1.5 text-xs font-medium text-uic-navy underline-offset-2 hover:underline"
              >
                <BookOpen size={14} aria-hidden="true" />
                {issue.guideline_title || 'UIC guideline'}
                <ExternalLink size={12} aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            )}
          </div>
        )}
      </div>
    </li>
  )
}

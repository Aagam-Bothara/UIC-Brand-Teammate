import { CircleCheck, Gauge, OctagonAlert, RefreshCw, TriangleAlert } from 'lucide-react'
import { useMemo } from 'react'
import { useText } from '../context/TextContext'
import type { ComplianceStatus } from '../types/api'
import IssueList from './compliance/IssueList'
import ScoreGauge from './compliance/ScoreGauge'
import { ReadingLevelTile } from './compliance/StatTiles'
import { SCORE_CAPTIONS, STATUS_META, estimateCurrentGrade, withAlpha } from './compliance/meta'

const STATUS_ICON: Record<ComplianceStatus, typeof CircleCheck> = {
  Approved: CircleCheck,
  'Minor Revisions Needed': TriangleAlert,
  'Major Revisions Needed': OctagonAlert,
}

const CARD = 'rounded-2xl border border-black/5 bg-white p-5 shadow-sm sm:p-6'

/** Task 4.7 — compliance dashboard (FR-7 scores + status, FR-8 issues). */
export default function ComplianceDisplay() {
  const { analysis, status, currentScores, currentText, openIssues, isStale, runAnalysis } = useText()

  const resolvedIssues = useMemo(() => {
    if (!analysis) return []
    const open = new Set(openIssues.map((i) => i.issue_id))
    return analysis.issues.filter((i) => !open.has(i.issue_id))
  }, [analysis, openIssues])

  const gradeNow = useMemo(() => (analysis ? estimateCurrentGrade(analysis, currentText) : 0), [analysis, currentText])

  if (status === 'loading') return <ComplianceSkeleton />

  if (!analysis || !currentScores) {
    return (
      <section aria-labelledby="compliance-heading" className={CARD}>
        <h2 id="compliance-heading" className="text-base font-semibold text-uic-navy">
          Compliance
        </h2>
        <div className="mt-4 flex flex-col items-center rounded-xl border border-dashed border-black/10 px-6 py-8 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-uic-navy/5 text-uic-navy">
            <Gauge size={22} aria-hidden="true" />
          </span>
          <p className="mt-3 text-sm font-semibold text-uic-navy">Your compliance score will appear here</p>
        </div>
      </section>
    )
  }

  const before = analysis.scores
  const now = currentScores
  const meta = STATUS_META[now.status]
  const Icon = STATUS_ICON[now.status]
  const statusChanged = before.status !== now.status

  return (
    <section aria-labelledby="compliance-heading" className={`@container ${CARD}`}>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <h2 id="compliance-heading" className="text-base font-semibold text-uic-navy">
          Compliance
        </h2>
        <p role="status" aria-live="polite" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-uic-steel/70">
          <span
            title={meta.meaning}
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-semibold"
            style={{ color: meta.text, backgroundColor: withAlpha(meta.color, 0.1) }}
          >
            <Icon size={16} aria-hidden="true" style={{ color: meta.color }} />
            {now.status}
          </span>
          <span className="sr-only">. {meta.meaning}</span>
          {statusChanged && <span>was {before.status}</span>}
        </p>
      </div>

      {isStale && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-uic-beach px-3 py-2 text-sm text-uic-steel">
          <span>Scores are from your last analysis.</span>
          <button
            type="button"
            onClick={() => void runAnalysis()}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-uic-navy hover:bg-black/[0.04]"
          >
            <RefreshCw size={14} aria-hidden="true" />
            Re-analyze
          </button>
        </div>
      )}

      <div className="mt-5 grid grid-cols-2 items-start gap-x-4 gap-y-6 @xl:grid-cols-3">
        <ScoreGauge label="Brand" caption={SCORE_CAPTIONS.brand} before={before.brand} now={now.brand} />
        <ScoreGauge label="Accessibility" caption={SCORE_CAPTIONS.accessibility} before={before.accessibility} now={now.accessibility} />
        <div className="col-span-2 @xl:col-span-1 @xl:self-center">
          <ReadingLevelTile
            before={before.reading_level.grade}
            now={gradeNow}
            target={before.reading_level.target}
            audience={before.reading_level.audience}
          />
        </div>
      </div>

      <div className="mt-5 border-t border-black/5 pt-4">
        <IssueList openIssues={openIssues} resolvedIssues={resolvedIssues} changes={analysis.changes} original={analysis.original} />
      </div>
    </section>
  )
}

function ComplianceSkeleton() {
  const block = 'animate-pulse rounded bg-black/5'
  return (
    <section aria-labelledby="compliance-heading" aria-busy="true" className={CARD}>
      <h2 id="compliance-heading" className="sr-only">
        Compliance score
      </h2>
      <p role="status" className="sr-only">
        Analyzing your draft…
      </p>
      <div className="flex items-center justify-between" aria-hidden="true">
        <div className={`${block} h-4 w-28`} />
        <div className={`${block} h-7 w-32 rounded-full`} />
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3" aria-hidden="true">
        {[0, 1].map((i) => (
          <div key={i} className="flex flex-col items-center gap-3">
            <div className="h-24 w-24 animate-pulse rounded-full border-[10px] border-black/5 sm:h-28 sm:w-28" />
            <div className={`${block} h-3 w-20`} />
          </div>
        ))}
        <div className={`${block} col-span-2 h-24 rounded-xl sm:col-span-1`} />
      </div>
      <div className={`${block} mt-5 h-10 rounded-xl`} aria-hidden="true" />
    </section>
  )
}

import { ArrowRight, FileText, Sparkles, Wand2 } from 'lucide-react'
import { RULESET_ORDER, RULESETS } from '../../config/rulesets'
import { tint } from './utils'
import PaneFrame from './PaneFrame'

const ruleColor = (i: number) => RULESETS[RULESET_ORDER[i % RULESET_ORDER.length]].highlight_color

/** Two little documents — a plain draft becoming a highlighted, polished version. */
function DraftIllustration() {
  const plain = ['w-full', 'w-11/12', 'w-full', 'w-3/4', 'w-10/12', 'w-2/3']
  return (
    <div aria-hidden="true" className="relative mx-auto mb-6 h-32 w-60">
      <div className="absolute top-3 left-2 flex h-28 w-24 -rotate-6 flex-col gap-2 rounded-xl border border-black/10 bg-white p-3 shadow-sm">
        <FileText size={14} className="mb-0.5 text-uic-steel/40" />
        {plain.map((w, i) => (
          <span key={i} className={`h-1.5 rounded-full bg-black/10 ${w}`} />
        ))}
      </div>
      <span className="absolute top-12 left-1/2 z-10 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full bg-uic-navy text-white shadow-md ring-4 ring-white">
        <ArrowRight size={16} />
      </span>
      <div className="absolute top-1 right-2 flex h-28 w-24 rotate-3 flex-col gap-2 rounded-xl border border-uic-navy/10 bg-white p-3 shadow-md">
        <Sparkles size={14} className="mb-0.5 text-uic-navy" />
        {plain.map((w, i) => {
          const marked = i === 0 || i === 2 || i === 4
          const color = ruleColor(i)
          return (
            <span
              key={i}
              className={`h-1.5 rounded-full ${w}`}
              style={marked ? { backgroundColor: tint(color, '80'), boxShadow: `0 2px 0 ${color}` } : { backgroundColor: 'rgb(0 0 0 / 0.1)' }}
            />
          )
        })}
      </div>
    </div>
  )
}

interface EmptyStateProps {
  onTrySample?: () => void
}

export function EmptyState({ onTrySample }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center px-2 py-6 text-center sm:py-10">
      <DraftIllustration />
      <h3 className="text-lg font-semibold tracking-tight text-uic-navy">Paste your draft and click Analyze</h3>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-uic-steel/70">
        See your original and the improved version side by side.
      </p>
      {onTrySample && (
        <button
          type="button"
          onClick={onTrySample}
          className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl border border-black/10 bg-white px-4 py-2 text-sm font-medium text-uic-navy shadow-sm transition hover:bg-black/[0.03]"
        >
          <Wand2 size={16} aria-hidden="true" />
          Try a sample announcement
        </button>
      )}
    </div>
  )
}

const LINE_WIDTHS = ['w-full', 'w-11/12', 'w-full', 'w-4/5', 'w-full', 'w-10/12', 'w-3/5']

/** Shown while analyzing: the draft on the left, a shimmering placeholder for the rewrite. */
export function LoadingState({ text }: { text: string }) {
  const lines = Math.min(14, Math.max(5, Math.ceil(text.length / 70)))
  return (
    <div aria-busy="true" className="mt-5">
      <div aria-hidden="true" className="mb-4 flex flex-wrap gap-2">
        {RULESET_ORDER.map((id) => (
          <span key={id} className="h-10 w-32 animate-pulse rounded-full bg-black/5" />
        ))}
      </div>
      <p role="status" className="mb-3 flex items-center gap-2 text-sm font-medium text-uic-navy">
        <Sparkles size={16} aria-hidden="true" className="animate-pulse" />
        Checking your draft against UIC guidelines…
      </p>
      <div className="grid gap-3 @2xl:grid-cols-2">
        <PaneFrame label="Original" tone="original" icon={<FileText size={14} aria-hidden="true" />} focusable>
          {text || ' '}
        </PaneFrame>
        <PaneFrame label="Improved" tone="improved" icon={<Sparkles size={14} aria-hidden="true" />} busy>
          <span className="sr-only">Generating the improved version…</span>
          <span aria-hidden="true" className="flex flex-col gap-3 py-1.5 whitespace-normal">
            {Array.from({ length: lines }, (_, i) => (
              <span key={i} className={`block h-3 animate-pulse rounded bg-black/5 ${LINE_WIDTHS[i % LINE_WIDTHS.length]}`} style={{ animationDelay: `${(i % 4) * 120}ms` }} />
            ))}
          </span>
        </PaneFrame>
      </div>
    </div>
  )
}

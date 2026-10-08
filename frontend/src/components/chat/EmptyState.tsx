import { ArrowUpRight, MessageCircleQuestion, Wand2 } from 'lucide-react'

interface EmptyStateProps {
  hasAnalysis: boolean
  /** Starter prompts (the caller passes at most three). */
  suggestions: string[]
  onPick: (prompt: string) => void
  disabled: boolean
}

/** Compact first-run state: one line on what the editor does, plus one-click starter prompts. */
export function EmptyState({ hasAnalysis, suggestions, onPick, disabled }: EmptyStateProps) {
  return (
    <div className="flex min-h-full flex-col justify-center px-1 py-4">
      <div className="mx-auto w-full max-w-sm">
        <span aria-hidden="true" className="grid size-10 place-items-center rounded-xl bg-uic-navy/[0.06] text-uic-navy">
          {hasAnalysis ? <Wand2 size={20} /> : <MessageCircleQuestion size={20} />}
        </span>
        <h3 className="mt-3 text-base font-semibold text-uic-navy">
          {hasAnalysis ? 'Want to fine-tune your draft?' : 'Hi! How can I help?'}
        </h3>
        <p className="mt-1 text-sm leading-relaxed text-uic-steel/75">
          {hasAnalysis ? 'Ask why something changed, or how to adjust the rewrite.' : 'Ask anything about UIC style, voice or accessibility.'}
        </p>
        <ul className="mt-4 space-y-1.5">
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onPick(s)}
                className="group flex min-h-10 w-full items-center gap-3 rounded-xl bg-uic-navy/[0.04] px-3.5 py-2 text-left text-sm text-uic-steel transition hover:bg-uic-navy/[0.08] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="flex-1">{s}</span>
                <ArrowUpRight size={16} aria-hidden="true" className="shrink-0 text-uic-navy/40 transition group-hover:text-uic-navy" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

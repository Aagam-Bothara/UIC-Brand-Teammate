import type { ReactNode, Ref, UIEventHandler } from 'react'

interface PaneFrameProps {
  label: string
  icon: ReactNode
  tone: 'original' | 'improved'
  meta?: ReactNode
  children: ReactNode
  /** Display classes for the outer frame (default `flex`; e.g. `hidden @2xl:flex` for an inactive mobile tab). */
  className?: string
  scrollRef?: Ref<HTMLDivElement>
  onScroll?: UIEventHandler<HTMLDivElement>
  /** Make the scroll region itself focusable (when it contains no focusable content). */
  focusable?: boolean
  busy?: boolean
}

/** A titled card for one side of the comparison, with a scrollable text body. */
export default function PaneFrame({
  label, icon, tone, meta, children, className = 'flex', scrollRef, onScroll, focusable, busy,
}: PaneFrameProps) {
  const improved = tone === 'improved'
  return (
    <div
      className={`min-w-0 flex-col overflow-hidden rounded-xl border ${
        improved ? 'border-uic-navy/10 bg-white shadow-sm' : 'border-black/5 bg-uic-expo/50'
      } ${className}`}
    >
      <div
        className={`flex items-center justify-between gap-3 border-b px-4 py-2.5 ${
          improved ? 'border-uic-navy/10 bg-uic-navy/[0.03]' : 'border-black/5'
        }`}
      >
        <span
          className={`flex items-center gap-2 text-xs font-medium uppercase tracking-wide ${
            improved ? 'text-uic-navy' : 'text-uic-steel/70'
          }`}
        >
          {icon}
          {label}
        </span>
        {meta && <span className="text-xs text-uic-steel/70 tabular-nums">{meta}</span>}
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        role="region"
        data-pane-scroll=""
        aria-label={`${label} text`}
        aria-busy={busy || undefined}
        tabIndex={focusable ? 0 : undefined}
        className={`max-h-[min(65vh,36rem)] min-h-40 overflow-y-auto overscroll-contain px-4 py-3.5 text-sm leading-7 break-words whitespace-pre-wrap sm:text-[15px] ${
          improved ? 'text-uic-steel' : 'text-uic-steel/80'
        }`}
      >
        {children}
      </div>
    </div>
  )
}

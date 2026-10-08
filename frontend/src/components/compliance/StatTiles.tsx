import { BookOpenText } from 'lucide-react'
import type { Audience } from '../../types/api'
import { DeltaChip } from './ScoreGauge'
import { STATUS_META } from './meta'

function Bar({ value, max, color, marker, ghost }: { value: number; max: number; color: string; marker?: number; ghost?: number }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`
  return (
    <div className="relative mt-3 h-2 rounded-full bg-black/[0.06]" aria-hidden="true">
      {ghost !== undefined && <div className="absolute inset-y-0 left-0 rounded-full bg-black/10" style={{ width: pct(ghost) }} />}
      <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ease-out" style={{ width: pct(value), backgroundColor: color }} />
      {marker !== undefined && (
        <div className="absolute -top-1 -bottom-1 w-0.5 rounded bg-uic-navy" style={{ left: pct(marker) }} />
      )}
    </div>
  )
}

export function ReadingLevelTile({ before, now, target, audience }: { before: number; now: number; target: number; audience: Audience }) {
  const max = Math.max(16, Math.ceil(Math.max(before, now, target)) + 2)
  const over = Math.round((now - target) * 10) / 10
  const tone = over <= 0 ? STATUS_META.Approved : over <= 2 ? STATUS_META['Minor Revisions Needed'] : STATUS_META['Major Revisions Needed']
  const changed = Math.abs(now - before) >= 0.05
  return (
    <div title={changed ? `Original draft: grade ${before.toFixed(1)}` : undefined}>
      <p className="flex items-center gap-1.5 text-sm font-semibold text-uic-navy">
        <BookOpenText size={16} aria-hidden="true" />
        Reading level
      </p>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5 text-uic-navy">
        <span className="text-2xl font-semibold tabular-nums">Grade {now.toFixed(1)}</span>
        {changed && <DeltaChip delta={now - before} digits={1} invert />}
        {changed && <span className="sr-only">(original {before.toFixed(1)})</span>}
      </p>
      <Bar value={now} max={max} color={tone.color} marker={target} ghost={changed ? before : undefined} />
      <p className="mt-2 text-xs text-uic-steel/70">
        Target grade {target} for {audience}
        {' · '}
        <span className="font-medium" style={{ color: tone.text }}>
          {over <= 0 ? 'On target' : `${over.toFixed(1)} above`}
        </span>
      </p>
    </div>
  )
}

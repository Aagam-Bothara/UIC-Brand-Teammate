import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { scoreTone, signed } from './meta'
import { useCountUp } from './useCountUp'

const R = 50
const STROKE = 10
const C = 2 * Math.PI * R

interface ScoreGaugeProps {
  label: string
  caption: string
  before: number
  now: number
}

/** Radial 0–100 gauge: animated arc for the current score, a notch marking the original draft's score. */
export default function ScoreGauge({ label, caption, before, now }: ScoreGaugeProps) {
  const shown = useCountUp(now)
  const tone = scoreTone(now)
  const delta = now - before
  const arc = Math.max(0, Math.min(100, shown)) / 100
  const notch = (before / 100) * 2 * Math.PI
  const nx = (r: number) => 60 + Math.cos(notch) * r
  const ny = (r: number) => 60 + Math.sin(notch) * r

  const trend =
    delta === 0 ? 'unchanged from the original draft' : `${delta > 0 ? 'up' : 'down'} ${Math.abs(delta)} from ${before} in the original draft`

  return (
    <div
      role="img"
      aria-label={`${label} score: ${now} out of 100, ${trend}. Covers ${caption.toLowerCase()}.`}
      title={`${caption} · original draft ${before}`}
      className="flex flex-col items-center text-center"
    >
      <div className="relative h-24 w-24 sm:h-28 sm:w-28">
        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" aria-hidden="true">
          <circle cx="60" cy="60" r={R} fill="none" stroke="rgba(0,0,0,0.06)" strokeWidth={STROKE} />
          {arc > 0 && (
            <circle
              cx="60"
              cy="60"
              r={R}
              fill="none"
              stroke={tone.color}
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${C * arc} ${C}`}
              style={{ transition: 'stroke 200ms ease' }}
            />
          )}
          {delta !== 0 && (
            <line x1={nx(R - 9)} y1={ny(R - 9)} x2={nx(R + 9)} y2={ny(R + 9)} stroke="#001E62" strokeOpacity={0.55} strokeWidth={2} strokeLinecap="round" />
          )}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-2xl font-semibold leading-none tracking-tight text-uic-navy tabular-nums sm:text-3xl">{Math.round(shown)}</span>
        </div>
      </div>
      <p className="mt-2 flex flex-wrap items-center justify-center gap-1.5 text-sm font-semibold text-uic-navy">
        {label}
        {Math.abs(delta) >= 0.5 && <DeltaChip delta={delta} />}
      </p>
    </div>
  )
}

export function DeltaChip({ delta, digits = 0, invert = false }: { delta: number; digits?: number; invert?: boolean }) {
  if (Math.abs(delta) < (digits ? 0.05 : 0.5)) {
    return <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-xs font-medium text-uic-steel/70">no change</span>
  }
  const good = invert ? delta < 0 : delta > 0
  const Icon = delta > 0 ? ArrowUpRight : ArrowDownRight
  return (
    <span
      className="inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums"
      style={{ backgroundColor: good ? '#E3F4EE' : '#FDE7EC', color: good ? '#00684B' : '#A30026' }}
    >
      <Icon size={12} aria-hidden="true" />
      {signed(delta, digits)}
    </span>
  )
}

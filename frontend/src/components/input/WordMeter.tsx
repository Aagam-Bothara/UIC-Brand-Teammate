import { MAX_WORDS } from '../../config/rulesets'
import { cx, fmt, type MeterTone } from './utils'

const FILL: Record<MeterTone, string> = {
  ok: 'bg-uic-navy/70',
  near: 'bg-[#B45309]',
  over: 'bg-uic-red',
}

/** Thin progress meter for words used against the SPEC FR-1 5,000-word limit. */
export default function WordMeter({ words, tone }: { words: number; tone: MeterTone }) {
  const pct = Math.min(100, (words / MAX_WORDS) * 100)
  return (
    <div
      role="meter"
      aria-label="Word limit used"
      aria-valuemin={0}
      aria-valuemax={MAX_WORDS}
      aria-valuenow={Math.min(words, MAX_WORDS)}
      aria-valuetext={`${fmt(words)} of ${fmt(MAX_WORDS)} words`}
      className="h-1.5 w-full overflow-hidden rounded-full bg-black/[0.06]"
    >
      <div
        className={cx('h-full rounded-full transition-[width,background-color] duration-200 ease-out', FILL[tone])}
        style={{ width: `${words > 0 ? Math.max(pct, 1.5) : 0}%` }}
      />
    </div>
  )
}

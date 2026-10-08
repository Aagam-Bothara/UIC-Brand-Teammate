import { useId, type ReactNode } from 'react'
import { cx } from './utils'

export interface SegmentOption<T extends string> {
  value: T
  label: string
  /** Longer description for assistive tech and the hover tooltip. */
  description?: string
  icon?: ReactNode
}

interface Props<T extends string> {
  legend: string
  value: T
  onChange: (value: T) => void
  options: SegmentOption<T>[]
  /** Extra content on the legend row (right aligned). */
  aside?: ReactNode
}

/**
 * Compact segmented control built from native radio inputs inside a labelled radiogroup, so it gets
 * radio semantics, arrow-key navigation and form labelling for free. The radios are visually hidden;
 * the label is the visual segment and shows the focus ring when its radio has keyboard focus.
 */
export default function SegmentedControl<T extends string>({ legend, value, onChange, options, aside }: Props<T>) {
  const name = useId()
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span id={`${name}-label`} className="w-16 shrink-0 text-[13px] text-uic-steel/70">
        {legend}
      </span>
      <div
        role="radiogroup"
        aria-labelledby={`${name}-label`}
        className="grid min-w-0 flex-1 gap-0.5 rounded-lg bg-black/[0.04] p-0.5"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {options.map((opt, i) => {
          const checked = opt.value === value
          // Index-based: option values may contain spaces ("Social Media"), which would split an
          // aria-describedby IDREF list and silently break the description.
          const descId = opt.description ? `${name}-opt${i}-desc` : undefined
          return (
            <label
              key={opt.value}
              title={opt.description}
              className={cx(
                'relative flex min-h-10 min-w-0 cursor-pointer select-none items-center justify-center gap-1.5 rounded-md px-1.5 text-center sm:px-2 text-[13px] font-medium transition duration-150 ease-out',
                'has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-1 has-[input:focus-visible]:outline-uic-navy',
                checked ? 'bg-white text-uic-navy shadow-sm' : 'text-uic-steel/75 hover:text-uic-steel active:scale-[0.98]',
              )}
            >
              <input
                type="radio"
                name={name}
                value={opt.value}
                checked={checked}
                onChange={() => onChange(opt.value)}
                aria-describedby={descId}
                className="sr-only"
              />
              {opt.icon && (
                <span aria-hidden="true" className={cx('hidden shrink-0 min-[400px]:inline-flex', checked ? 'text-uic-navy' : 'text-uic-steel/55')}>
                  {opt.icon}
                </span>
              )}
              <span className="truncate">{opt.label}</span>
              {opt.description && (
                // `hidden` keeps it out of the label's accessible name; aria-describedby still reads it.
                <span id={descId} hidden>
                  {opt.description}
                </span>
              )}
            </label>
          )
        })}
      </div>
      {aside}
    </div>
  )
}

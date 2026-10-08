import { Check } from 'lucide-react'
import { useId } from 'react'
import type { RulesetInfo } from '../../types/api'
import { cx } from './utils'

interface Props {
  ruleset: RulesetInfo
  checked: boolean
  onToggle: () => void
}

/**
 * One ruleset as a compact toggle chip: a native checkbox (visually hidden) labelled by the ruleset
 * name; the description is a tooltip and the accessible description. The color dot is always paired
 * with the text name (WCAG 1.4.1) and the check mark shows state by shape, not color alone.
 */
export default function RulesetToggle({ ruleset, checked, onToggle }: Props) {
  const id = useId()
  const color = ruleset.highlight_color
  return (
    <label
      htmlFor={id}
      title={ruleset.description}
      className={cx(
        'inline-flex min-h-10 cursor-pointer select-none items-center gap-2 rounded-full border px-3 text-[13px] font-medium transition duration-150 ease-out',
        'has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-uic-navy',
        'active:scale-[0.98]',
        checked ? 'text-uic-navy' : 'border-black/10 bg-white text-uic-steel/70 hover:border-black/20',
      )}
      style={checked ? { borderColor: `${color}80`, backgroundColor: `${color}12` } : undefined}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        aria-labelledby={`${id}-name`}
        aria-describedby={`${id}-desc`}
        className="sr-only"
      />
      <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ backgroundColor: color, opacity: checked ? 1 : 0.45 }} />
      <span id={`${id}-name`}>{ruleset.ruleset_name}</span>
      <span id={`${id}-desc`} hidden>
        {ruleset.description}
      </span>
      <Check
        size={13}
        strokeWidth={3}
        aria-hidden="true"
        className={cx('-mr-0.5 shrink-0 transition duration-150', checked ? 'opacity-100' : 'w-0 opacity-0')}
        style={checked ? { color } : undefined}
      />
    </label>
  )
}

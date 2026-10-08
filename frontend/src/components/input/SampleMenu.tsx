import { ChevronDown, Sparkles, Star } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { DEMO_SAMPLES, type DemoSample } from '../../data/demoSamples'
import { cx } from './utils'

const STATUS_SHORT: Record<string, string> = {
  'Major Revisions Needed': 'Major',
  'Minor Revisions Needed': 'Minor',
  Approved: 'Clean',
}

interface Props {
  onPick: (sample: DemoSample) => void
  className: string
}

/**
 * "Try a sample" menu: synthetic UIC drafts generated from Team8Dataset (data/demo/). Featured
 * demo drafts first, then all examples. Menu-button pattern: arrows, Home/End, Esc, click outside.
 */
export default function SampleMenu({ onPick, className }: Props) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  const featured = DEMO_SAMPLES.filter((s) => s.featured)
  const rest = DEMO_SAMPLES.filter((s) => !s.featured)

  useEffect(() => {
    if (!open) return
    menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus()
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node) && !btnRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const close = (refocus = true) => {
    setOpen(false)
    if (refocus) btnRef.current?.focus()
  }

  const onMenuKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])]
    const i = items.indexOf(document.activeElement as HTMLButtonElement)
    const go = (n: number) => {
      e.preventDefault()
      items[(n + items.length) % items.length]?.focus()
    }
    if (e.key === 'ArrowDown') go(i + 1)
    else if (e.key === 'ArrowUp') go(i - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(items.length - 1)
    else if (e.key === 'Escape') {
      e.preventDefault()
      close()
    } else if (e.key === 'Tab') close(false)
  }

  const pick = (s: DemoSample) => {
    close()
    onPick(s)
  }

  const item = (s: DemoSample) => (
    <button
      key={s.id}
      type="button"
      role="menuitem"
      onClick={() => pick(s)}
      className="flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left hover:bg-black/[0.04] focus-visible:bg-black/[0.04] focus-visible:outline-none"
    >
      <span className="text-[13px] font-medium text-uic-navy">{s.title}</span>
      <span className="text-[11px] text-uic-steel/70">
        {s.audience} · {s.channel} · {STATUS_SHORT[s.status_hint] ?? s.status_hint}
      </span>
    </button>
  )

  return (
    <div className="relative">
      <button
        ref={btnRef}
        type="button"
        className={className}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            setOpen(true)
          }
        }}
        title="Load an example UIC draft"
      >
        <Sparkles size={15} aria-hidden="true" />
        Try a sample
        <ChevronDown size={14} aria-hidden="true" className={cx('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Sample drafts"
          onKeyDown={onMenuKey}
          className="absolute right-0 z-30 mt-1 max-h-[min(26rem,60vh)] w-[min(22rem,calc(100vw-2rem))] overflow-auto rounded-xl border border-black/10 bg-white p-1.5 shadow-lg"
        >
          <p className="flex items-center gap-1.5 px-3 pb-1 pt-1.5 text-[11px] font-medium text-uic-steel/70">
            <Star size={12} aria-hidden="true" /> Featured
          </p>
          {featured.map(item)}
          <div role="separator" className="my-1.5 border-t border-black/5" />
          <p className="px-3 pb-1 text-[11px] font-medium text-uic-steel/70">More examples</p>
          {rest.map(item)}
        </div>
      )}
    </div>
  )
}

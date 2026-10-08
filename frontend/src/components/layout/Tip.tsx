import type { ReactNode } from 'react'

/**
 * Small visual tooltip shown on hover and keyboard focus of its trigger. display:none until then, so
 * it never widens the page. Purely decorative
 * (aria-hidden): the trigger must carry its own accessible name.
 */
export default function Tip({ text, align = 'center', children }: { text: ReactNode; align?: 'start' | 'center' | 'end'; children: ReactNode }) {
  const pos = align === 'start' ? 'left-0' : align === 'end' ? 'right-0' : 'left-1/2 -translate-x-1/2'
  return (
    <span className="group/tip relative inline-flex">
      {children}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute top-full z-50 mt-2 hidden w-max max-w-[min(15rem,calc(100vw-2rem))] rounded-lg bg-uic-navy px-2.5 py-1.5 text-xs leading-snug font-medium text-white shadow-md group-hover/tip:block group-has-[:focus-visible]/tip:block ${pos}`}
      >
        {text}
      </span>
    </span>
  )
}

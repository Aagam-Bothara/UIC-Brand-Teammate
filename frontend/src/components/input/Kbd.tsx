import type { ReactNode } from 'react'

/** Keyboard key cap, e.g. <Kbd>⌘</Kbd>. */
export default function Kbd({ children, tone = 'light' }: { children: ReactNode; tone?: 'light' | 'dark' }) {
  return (
    <kbd
      className={
        tone === 'dark'
          ? 'inline-flex min-w-[1.5rem] items-center justify-center rounded-md border border-white/25 bg-white/10 px-1.5 py-px font-sans text-[11px] font-medium text-white/90'
          : 'inline-flex min-w-[1.5rem] items-center justify-center rounded-md border border-black/10 border-b-black/20 bg-white px-1.5 py-px font-sans text-[11px] font-medium text-uic-steel/80 shadow-[0_1px_0_rgba(0,0,0,0.04)]'
      }
    >
      {children}
    </kbd>
  )
}

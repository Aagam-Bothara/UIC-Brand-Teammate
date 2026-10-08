/** Shared class strings for app-shell buttons (DESIGN.md "Buttons"). */
const base =
  'inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50'

export const btnPrimary = `${base} bg-uic-navy text-white shadow-sm hover:bg-uic-navy/90`
export const btnSecondary = `${base} border border-black/10 bg-white text-uic-navy shadow-sm hover:bg-black/[0.03]`
export const btnDanger = `${base} bg-uic-red text-white shadow-sm hover:bg-uic-red/90`
export const btnGhost = `${base} text-uic-navy hover:bg-black/[0.04]`

/** Is the user asking for reduced motion? Safe outside browsers. */
export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** Focus the draft textarea in the input column, if present. */
export function focusDraftInput(): void {
  document.querySelector<HTMLElement>('[data-region="input"] textarea')?.focus()
}

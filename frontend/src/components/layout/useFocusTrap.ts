import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',')

export function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => !el.closest('[inert]') && !el.closest('[aria-hidden="true"]'),
  )
}

let scrollLocks = 0
let savedOverflow = ''

function lockScroll() {
  if (scrollLocks++ === 0) {
    savedOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
}

function unlockScroll() {
  if (--scrollLocks === 0) document.body.style.overflow = savedOverflow
}

interface FocusTrapOptions {
  onEscape?: () => void
  /** Element to focus on activation; defaults to the first focusable element, then the container. */
  initialFocus?: (container: HTMLElement) => HTMLElement | null | undefined
  lockScroll?: boolean
  /** Where focus goes on deactivation when the previously focused element can no longer take it. */
  restoreFocusFallback?: () => HTMLElement | null
}

/** Active traps, innermost last: only the top one handles keys. */
const trapStack: HTMLElement[] = []

/**
 * While `active`: keeps Tab/Shift+Tab inside `ref`, calls `onEscape` on Esc, optionally locks body
 * scroll. On deactivation (or unmount) focus returns to whatever was focused before activation.
 * Esc and Tab still work if focus escaped the container (e.g. the user clicked a toast while a
 * drawer was open).
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean, options: FocusTrapOptions = {}) {
  const opts = useRef(options)
  useEffect(() => {
    opts.current = options
  })

  useEffect(() => {
    const container = ref.current
    if (!active || !container) return

    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const target = opts.current.initialFocus?.(container) ?? getFocusable(container)[0] ?? container
    target.focus()
    // The container may still be mid-transition (e.g. visibility) and refuse focus: retry next frame.
    let frame = 0
    if (document.activeElement !== target) {
      frame = requestAnimationFrame(() => {
        if (!container.contains(document.activeElement)) target.focus()
      })
    }
    const locked = opts.current.lockScroll ?? false
    if (locked) lockScroll()
    trapStack.push(container)

    const onKeyDown = (e: KeyboardEvent) => {
      if (trapStack[trapStack.length - 1] !== container) return
      if (e.key === 'Escape') {
        if (e.defaultPrevented) return
        e.stopPropagation()
        opts.current.onEscape?.()
        return
      }
      if (e.key !== 'Tab') return
      const items = getFocusable(container)
      if (items.length === 0) {
        e.preventDefault()
        container.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const current = document.activeElement
      if (!container.contains(current)) {
        e.preventDefault()
        ;(e.shiftKey ? last : first).focus()
      } else if (e.shiftKey && (current === first || current === container)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && current === last) {
        e.preventDefault()
        first.focus()
      }
    }
    // Focus escaped the container (e.g. a click on a toast): still honour Esc and pull Tab back in.
    const onDocumentKeyDown = (e: KeyboardEvent) => {
      if (!(e.target instanceof Node) || !container.contains(e.target)) onKeyDown(e)
    }
    container.addEventListener('keydown', onKeyDown)
    document.addEventListener('keydown', onDocumentKeyDown)

    return () => {
      cancelAnimationFrame(frame)
      container.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('keydown', onDocumentKeyDown)
      const i = trapStack.lastIndexOf(container)
      if (i !== -1) trapStack.splice(i, 1)
      if (locked) unlockScroll()
      if (previouslyFocused?.isConnected) previouslyFocused.focus()
      // e.g. the launcher was hidden by a resize across a breakpoint while the trap was active.
      if (!previouslyFocused || document.activeElement !== previouslyFocused) opts.current.restoreFocusFallback?.()?.focus()
    }
  }, [active, ref])
}

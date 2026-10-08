import { useEffect, useRef, useState } from 'react'

function motionAllowed(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    typeof window.requestAnimationFrame === 'function' &&
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Animates a number toward `target` (ease-out cubic). Starts from `from` on mount, then from the
 * last shown value on every change. Jumps straight to the target when reduced motion is preferred.
 */
export function useCountUp(target: number, { from = 0, durationMs = 800 } = {}): number {
  const [value, setValue] = useState(() => (motionAllowed() ? from : target))
  const shown = useRef(value)

  useEffect(() => {
    if (!motionAllowed()) {
      shown.current = target
      return
    }
    const start = shown.current
    if (start === target) return
    let raf = 0
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / durationMs)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = start + (target - start) * eased
      shown.current = v
      setValue(v)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, durationMs])

  // Reduced motion: show the target directly (derived during render, no extra state update).
  return motionAllowed() ? value : target
}

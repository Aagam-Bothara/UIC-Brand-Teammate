/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { RULESET_ORDER } from '../config/rulesets'
import { sanitizeRulesetIds } from '../lib/sanitize'
import { usePersistentState } from '../lib/usePersistentState'
import type { RulesetId } from '../types/api'

export interface Toast {
  id: number
  message: string
  tone: 'info' | 'success' | 'error'
}

/** View state: progressive reveal, highlights, selected change, toasts (Task 4.3). */
export interface UIContextValue {
  /** Rulesets whose changes are revealed in the rewrite (FR-5 progressive reveal). */
  revealed: ReadonlySet<RulesetId>
  toggleReveal: (id: RulesetId) => void
  setRevealed: (ids: RulesetId[]) => void
  revealAll: () => void
  revealNone: () => void
  /** Reveal the next not-yet-revealed ruleset (SPEC order) among `available`; returns it or null. */
  revealNext: (available: RulesetId[]) => RulesetId | null
  showHighlights: boolean
  setShowHighlights: (v: boolean) => void
  /** Change whose explanation is open (FR-9). */
  selectedChangeId: string | null
  selectChange: (id: string | null) => void
  toasts: Toast[]
  notify: (message: string, tone?: Toast['tone']) => void
  dismissToast: (id: number) => void
}

const UIContext = createContext<UIContextValue | null>(null)

let toastSeq = 0

export function UIProvider({ children }: { children: ReactNode }) {
  const [revealedList, setRevealedList] = usePersistentState<RulesetId[]>('revealed', [...RULESET_ORDER], sanitizeRulesetIds)
  const [showHighlights, setShowHighlights] = usePersistentState<boolean>('showHighlights', true, (v) =>
    typeof v === 'boolean' ? v : null,
  )
  const [selectedChangeId, selectChange] = useState<string | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const toggleReveal = useCallback(
    (id: RulesetId) =>
      setRevealedList((prev) => RULESET_ORDER.filter((r) => (r === id ? !prev.includes(r) : prev.includes(r)))),
    [setRevealedList],
  )
  const setRevealed = useCallback((ids: RulesetId[]) => setRevealedList(RULESET_ORDER.filter((r) => ids.includes(r))), [setRevealedList])
  const revealAll = useCallback(() => setRevealedList([...RULESET_ORDER]), [setRevealedList])
  const revealNone = useCallback(() => setRevealedList([]), [setRevealedList])
  const revealNext = useCallback(
    (available: RulesetId[]) => {
      const next = RULESET_ORDER.find((r) => available.includes(r) && !revealedList.includes(r)) ?? null
      if (next) setRevealedList((prev) => RULESET_ORDER.filter((r) => r === next || prev.includes(r)))
      return next
    },
    [revealedList, setRevealedList],
  )

  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const notify = useCallback(
    (message: string, tone: Toast['tone'] = 'info') => {
      const id = ++toastSeq
      setToasts((t) => [...t.slice(-2), { id, message, tone }])
      // Errors stay longer so they can be read; success/info clear quickly.
      setTimeout(() => dismissToast(id), tone === 'error' ? 7000 : 4000)
    },
    [dismissToast],
  )

  const value = useMemo<UIContextValue>(
    () => ({
      revealed: new Set(revealedList), toggleReveal, setRevealed, revealAll, revealNone, revealNext,
      showHighlights, setShowHighlights, selectedChangeId, selectChange, toasts, notify, dismissToast,
    }),
    [revealedList, toggleReveal, setRevealed, revealAll, revealNone, revealNext, showHighlights, setShowHighlights, selectedChangeId, toasts, notify, dismissToast],
  )
  return <UIContext.Provider value={value}>{children}</UIContext.Provider>
}

export function useUI(): UIContextValue {
  const ctx = useContext(UIContext)
  if (!ctx) throw new Error('useUI must be used inside <UIProvider>')
  return ctx
}

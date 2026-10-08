/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { AUDIENCES, RULESET_ORDER, RULESETS } from '../config/rulesets'
import { sanitizeAudience, sanitizeChannel, sanitizeRulesetIds } from '../lib/sanitize'
import { usePersistentState } from '../lib/usePersistentState'
import { getAudiences, getRules } from '../services/api'
import type { Audience, AudienceInfo, Channel, RulesetId, RulesetInfo } from '../types/api'

/** Analysis settings: audience, channel and which rulesets to check (Task 4.3). */
export interface RulesetContextValue {
  audience: Audience
  setAudience: (a: Audience) => void
  channel: Channel
  setChannel: (c: Channel) => void
  /** Rulesets sent to /api/analyze, in SPEC order. */
  selectedRulesets: RulesetId[]
  toggleRuleset: (id: RulesetId) => void
  setSelectedRulesets: (ids: RulesetId[]) => void
  /** Ruleset metadata (from GET /api/rules, falling back to config). SPEC order. */
  rulesets: RulesetInfo[]
  rulesetById: Record<RulesetId, RulesetInfo>
  audiences: AudienceInfo[]
}

const RulesetContext = createContext<RulesetContextValue | null>(null)

const inOrder = (ids: RulesetId[]) => RULESET_ORDER.filter((id) => ids.includes(id))

export function RulesetProvider({ children }: { children: ReactNode }) {
  const [audience, setAudience] = usePersistentState<Audience>('audience', 'Students', sanitizeAudience)
  const [channel, setChannel] = usePersistentState<Channel>('channel', 'Email', sanitizeChannel)
  const [selected, setSelected] = usePersistentState<RulesetId[]>('rulesets', [...RULESET_ORDER], sanitizeRulesetIds)
  const [rulesets, setRulesets] = useState<RulesetInfo[]>(() => RULESET_ORDER.map((id) => RULESETS[id]))
  const [audiences, setAudiences] = useState<AudienceInfo[]>(AUDIENCES)

  useEffect(() => {
    let alive = true
    getRules().then((r) => alive && setRulesets(r))
    getAudiences().then((a) => alive && setAudiences(a))
    return () => {
      alive = false
    }
  }, [])

  const toggleRuleset = useCallback(
    (id: RulesetId) => setSelected((prev) => inOrder(prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])),
    [setSelected],
  )
  const setSelectedRulesets = useCallback((ids: RulesetId[]) => setSelected(inOrder(ids)), [setSelected])

  const value = useMemo<RulesetContextValue>(() => {
    const rulesetById = { ...RULESETS }
    for (const r of rulesets) rulesetById[r.ruleset_id] = r
    return {
      audience, setAudience, channel, setChannel,
      selectedRulesets: inOrder(selected), toggleRuleset, setSelectedRulesets,
      rulesets, rulesetById, audiences,
    }
  }, [audience, setAudience, channel, setChannel, selected, toggleRuleset, setSelectedRulesets, rulesets, audiences])

  return <RulesetContext.Provider value={value}>{children}</RulesetContext.Provider>
}

export function useRulesets(): RulesetContextValue {
  const ctx = useContext(RulesetContext)
  if (!ctx) throw new Error('useRulesets must be used inside <RulesetProvider>')
  return ctx
}

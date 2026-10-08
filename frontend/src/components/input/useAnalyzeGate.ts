import { useMemo } from 'react'
import { MAX_CHARS, MAX_WORDS } from '../../config/rulesets'
import { useRulesets } from '../../context/RulesetContext'
import { useText } from '../../context/TextContext'
import { countWords } from '../../lib/changes'
import { fmt } from './utils'

export interface AnalyzeGate {
  words: number
  chars: number
  /** Over the SPEC FR-1 limit (5,000 words) or the backend character limit. */
  overLimit: boolean
  /** Why analysis can't run right now (null when it can, ignoring an in-flight run). */
  reason: string | null
  /** True when the Analyze action is available (has text, within limits, ≥1 ruleset, not loading). */
  canAnalyze: boolean
}

/**
 * Single source of truth for "can we analyze?" — shared by the Analyze button (RulesetPanel)
 * and the Cmd/Ctrl+Enter shortcut (TextInput) so both always agree and show the same reason.
 */
export function useAnalyzeGate(): AnalyzeGate {
  const { text, status } = useText()
  const { selectedRulesets } = useRulesets()
  const words = useMemo(() => countWords(text), [text])
  const chars = text.length
  const overLimit = words > MAX_WORDS || chars > MAX_CHARS

  let reason: string | null = null
  if (!text.trim()) reason = 'Add your draft above to analyze it.'
  else if (words > MAX_WORDS) reason = `Your draft is over the ${fmt(MAX_WORDS)}-word limit. Shorten it to analyze.`
  else if (chars > MAX_CHARS) reason = `Your draft is over the ${fmt(MAX_CHARS)}-character limit. Shorten it to analyze.`
  else if (selectedRulesets.length === 0) reason = 'Turn on at least one check to analyze.'

  return { words, chars, overLimit, reason, canAnalyze: !reason && status !== 'loading' }
}

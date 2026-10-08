/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { applyChanges, isChangeApplied, normalizeChanges, type ChangeDecision, type Decisions } from '../lib/changes'
import { sanitizeAnalysis, sanitizeChat, sanitizeDecisions } from '../lib/sanitize'
import { computeScores } from '../lib/scoring'
import { usePersistentState } from '../lib/usePersistentState'
import { analyze, refine, toApiError } from '../services/api'
import type { AnalyzeResponse, ApiError, Change, ChatMessage, Issue, Scores } from '../types/api'
import { useRulesets } from './RulesetContext'
import { useUI } from './UIContext'

export type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error'

/** Draft text, analysis result, per-change decisions and chat (Task 4.3). */
export interface TextContextValue {
  text: string
  setText: (t: string) => void
  analysis: AnalyzeResponse | null
  status: AnalysisStatus
  error: ApiError | null
  /** True when the draft or settings changed since the last analysis. */
  isStale: boolean
  runAnalysis: () => Promise<void>
  cancelAnalysis: () => void
  /** Individual accept/reject overrides (FR-10). */
  decisions: Decisions
  setDecision: (changeId: string, decision: ChangeDecision | null) => void
  resetDecisions: () => void
  /** Original with the currently applied changes (revealed rulesets + decisions). */
  currentText: string
  /** Issues not resolved by an applied change. */
  openIssues: Issue[]
  /** Scores recomputed for the current text (projected). Null before analysis. */
  currentScores: Scores | null
  chat: ChatMessage[]
  chatPending: boolean
  sendChat: (message: string) => Promise<void>
  clearChat: () => void
  /** Clear draft, analysis, decisions and chat. */
  reset: () => void
}

const TextContext = createContext<TextContextValue | null>(null)

const now = () => new Date().toISOString()
let msgSeq = 0
const msg = (role: ChatMessage['role'], content: string, extra?: Partial<ChatMessage>): ChatMessage => ({
  id: `m${Date.now()}-${++msgSeq}`, role, content, created_at: now(), ...extra,
})

const sameSet = (a: readonly string[], b: readonly string[]) => {
  const sa = new Set(a)
  const sb = new Set(b)
  return sa.size === sb.size && [...sa].every((x) => sb.has(x))
}

export function TextProvider({ children }: { children: ReactNode }) {
  const { audience, channel, selectedRulesets } = useRulesets()
  const { revealed, revealAll, selectChange, notify } = useUI()
  const [text, setText] = usePersistentState<string>('text', '', (v) => (typeof v === 'string' ? v : null))
  const [analysis, setAnalysis] = usePersistentState<AnalyzeResponse | null>('analysis', null, sanitizeAnalysis)
  // Restored decisions only count for changes in the restored analysis.
  const [decisions, setDecisions] = usePersistentState<Decisions>('decisions', {}, (v) => sanitizeDecisions(v, analysis))
  const [chat, setChat] = usePersistentState<ChatMessage[]>('chat', [], sanitizeChat)
  const [status, setStatus] = useState<AnalysisStatus>(analysis ? 'success' : 'idle')
  const [error, setError] = useState<ApiError | null>(null)
  const [chatPending, setChatPending] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  /** Bumped when an analysis starts, is replaced or reset: results from older requests are dropped. */
  const analysisGen = useRef(0)
  /** Bumped when the conversation is cleared or reset: replies to it are dropped. */
  const chatGen = useRef(0)
  /** Synchronous guard so two sends in the same tick can't both start (state updates lag a render). */
  const chatBusy = useRef(false)

  const runAnalysis = useCallback(async () => {
    if (!text.trim() || selectedRulesets.length === 0) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const gen = ++analysisGen.current
    setStatus('loading')
    setError(null)
    try {
      const result = await analyze({ text, audience, channel, rulesets: selectedRulesets }, ctrl.signal)
      if (ctrl.signal.aborted || gen !== analysisGen.current) return
      setAnalysis(result)
      setDecisions({})
      selectChange(null)
      revealAll()
      setStatus('success')
    } catch (e) {
      if (ctrl.signal.aborted || gen !== analysisGen.current) return
      setError(toApiError(e))
      setStatus('error')
    }
  }, [text, audience, channel, selectedRulesets, setAnalysis, setDecisions, selectChange, revealAll])

  const cancelAnalysis = useCallback(() => {
    const ctrl = abortRef.current
    if (!ctrl || ctrl.signal.aborted) return
    ctrl.abort()
    // Only a running analysis is cancelled; an error or success state is left as it is.
    setStatus((s) => (s === 'loading' ? (analysis ? 'success' : 'idle') : s))
  }, [analysis])

  const setDecision = useCallback(
    (changeId: string, decision: ChangeDecision | null) =>
      setDecisions((prev) => {
        const next = { ...prev }
        if (decision) next[changeId] = decision
        else delete next[changeId]
        return next
      }),
    [setDecisions],
  )
  const resetDecisions = useCallback(() => setDecisions({}), [setDecisions])

  const derived = useMemo(() => {
    if (!analysis) return { currentText: text, openIssues: [] as Issue[], currentScores: null as Scores | null }
    const applied = (c: Change) => isChangeApplied(c, revealed, decisions)
    // Same normalisation as the rendered rewrite: a dropped (overlapping / out-of-range) change
    // must not count as fixing its issue.
    const changes = normalizeChanges(analysis.original, analysis.changes)
    const currentText = applyChanges(analysis.original, changes, applied)
    // An issue is resolved only when EVERY change that addresses it is applied.
    const fixed = new Map<string, boolean>()
    for (const c of changes) {
      const on = applied(c)
      for (const id of c.issue_ids) fixed.set(id, (fixed.get(id) ?? true) && on)
    }
    const openIssues = analysis.issues.filter((i) => fixed.get(i.issue_id) !== true)
    const currentScores: Scores = { ...computeScores(openIssues), reading_level: analysis.scores.reading_level }
    return { currentText, openIssues, currentScores }
  }, [analysis, text, revealed, decisions])

  const isStale =
    !!analysis &&
    (analysis.original !== text ||
      analysis.audience !== audience ||
      analysis.channel !== channel ||
      !sameSet(analysis.rulesets, selectedRulesets))

  const sendChat = useCallback(
    async (message: string) => {
      const content = message.trim()
      if (!content || chatBusy.current) return
      chatBusy.current = true
      const cGen = chatGen.current
      const aGen = analysisGen.current
      const userMsg = msg('user', content)
      setChat((prev) => [...prev, userMsg])
      setChatPending(true)
      try {
        const res = await refine({
          message: content,
          original: analysis?.original ?? text,
          current_text: derived.currentText,
          audience, channel, rulesets: selectedRulesets,
          history: chat.slice(-10).map(({ role, content }) => ({ role, content })),
          analysis_id: analysis?.analysis_id ?? null,
        })
        if (cGen !== chatGen.current) return // conversation was cleared / reset meanwhile
        setChat((prev) => [...prev, msg('assistant', res.reply, res.guidelines?.length ? { guidelines: res.guidelines } : undefined)])
        if (res.analysis) {
          if (aGen === analysisGen.current) {
            // Newest request wins: supersede any analysis that was already running.
            analysisGen.current++
            abortRef.current?.abort()
            setAnalysis(res.analysis)
            setDecisions({})
            selectChange(null)
            revealAll()
            setError(null)
            setStatus('success')
            notify('Rewrite updated from your request', 'success')
          } else {
            notify('Your draft was re-analyzed while that reply was on its way, so its rewrite wasn’t applied.', 'info')
          }
        }
      } catch (e) {
        if (cGen !== chatGen.current) return
        const err = toApiError(e)
        setChat((prev) => [...prev, msg('assistant', `Sorry — ${err.message}`, { error: true })])
      } finally {
        if (cGen === chatGen.current) {
          chatBusy.current = false
          setChatPending(false)
        }
      }
    },
    [setChat, analysis, text, derived.currentText, audience, channel, selectedRulesets, chat, setAnalysis, setDecisions, selectChange, revealAll, notify],
  )

  /** Forget the conversation, including any reply still on its way. */
  const dropChat = useCallback(() => {
    chatGen.current++
    chatBusy.current = false
    setChatPending(false)
    setChat([])
  }, [setChat])
  const clearChat = dropChat

  const reset = useCallback(() => {
    abortRef.current?.abort()
    analysisGen.current++
    dropChat()
    setText('')
    setAnalysis(null)
    setDecisions({})
    setError(null)
    setStatus('idle')
    selectChange(null)
  }, [dropChat, setText, setAnalysis, setDecisions, selectChange])

  const value = useMemo<TextContextValue>(
    () => ({
      text, setText, analysis, status, error, isStale, runAnalysis, cancelAnalysis,
      decisions, setDecision, resetDecisions, ...derived,
      chat, chatPending, sendChat, clearChat, reset,
    }),
    [text, setText, analysis, status, error, isStale, runAnalysis, cancelAnalysis, decisions, setDecision, resetDecisions, derived, chat, chatPending, sendChat, clearChat, reset],
  )
  return <TextContext.Provider value={value}>{children}</TextContext.Provider>
}

export function useText(): TextContextValue {
  const ctx = useContext(TextContext)
  if (!ctx) throw new Error('useText must be used inside <TextProvider>')
  return ctx
}

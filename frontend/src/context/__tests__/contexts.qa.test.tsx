/**
 * QA regression tests for the state layer: localStorage restore of corrupt / old-shape data, races
 * between analyze / chat / reset, isStale and the derived currentText / openIssues / scores.
 */
import { act, render, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { analyze, refine } from '../../services/api'
import { mockAnalyze } from '../../services/mockData'
import type { AnalyzeRequest, AnalyzeResponse, Change, Issue, RefineResponse } from '../../types/api'
import { RulesetProvider, useRulesets } from '../RulesetContext'
import { TextProvider, useText } from '../TextContext'
import { UIProvider, useUI } from '../UIContext'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  return { ...actual, analyze: vi.fn(), refine: vi.fn() }
})

const KEY = (k: string) => `uic-editorial:${k}`
const wrapper = ({ children }: { children: ReactNode }) => (
  <RulesetProvider>
    <UIProvider>
      <TextProvider>{children}</TextProvider>
    </UIProvider>
  </RulesetProvider>
)
const useAll = () => ({ text: useText(), rules: useRulesets(), ui: useUI() })

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const chg = (id: string, s: number, e: number, rewritten: string, issue_ids: string[]): Change => ({
  change_id: id, ruleset: 'brand', original_start: s, original_end: e, original_text: '', rewritten_text: rewritten,
  explanation: '', issue_ids,
})
const iss = (id: string, extra: Partial<Issue> = {}): Issue => ({
  issue_id: id, ruleset: 'brand', rule_id: `r-${id}`, severity: 'high', message: '', start: 0, end: 0, excerpt: '', ...extra,
})
function analysisFor(text: string, changes: Change[], issues: Issue[], extra: Partial<AnalyzeResponse> = {}): AnalyzeResponse {
  return {
    ...mockAnalyze({ text, audience: 'Students', channel: 'Email', rulesets: ['brand', 'accessibility', 'content', 'reading_level', 'audience_tone'] }),
    changes, issues, ...extra,
  }
}

beforeEach(() => {
  vi.mocked(analyze).mockReset()
  vi.mocked(refine).mockReset()
  vi.mocked(analyze).mockImplementation(async (req: AnalyzeRequest) => mockAnalyze(req))
})

describe('restoring persisted state', () => {
  it('survives corrupt / old-shape values for every key instead of crashing on load', () => {
    localStorage.setItem(KEY('text'), '42')
    localStorage.setItem(KEY('analysis'), JSON.stringify({ original: 'Hi', analysis_id: 'old' })) // no changes/issues/scores
    localStorage.setItem(KEY('decisions'), 'null')
    localStorage.setItem(KEY('chat'), '{"oops":true}')
    localStorage.setItem(KEY('audience'), '"Alumni"')
    localStorage.setItem(KEY('channel'), '7')
    localStorage.setItem(KEY('rulesets'), 'null')
    localStorage.setItem(KEY('revealed'), '"brand"')
    localStorage.setItem(KEY('showHighlights'), '"yes"')
    const { result } = renderHook(useAll, { wrapper })
    expect(result.current.text.text).toBe('')
    expect(result.current.text.analysis).toBeNull()
    expect(result.current.text.chat).toEqual([])
    expect(result.current.text.decisions).toEqual({})
    expect(result.current.rules.audience).toBe('Students')
    expect(result.current.rules.channel).toBe('Email')
    expect(result.current.rules.selectedRulesets).toHaveLength(5)
    expect([...result.current.ui.revealed]).toHaveLength(5)
    expect(result.current.ui.showHighlights).toBe(true)
  })

  it('restores an older analysis missing new fields, and drops decisions for unknown changes', () => {
    const a = analysisFor('Hello UIC', [chg('c1', 6, 9, 'University of Illinois Chicago', ['i1'])], [iss('i1')])
    const { scores: _s, guidelines: _g, ...old } = a
    localStorage.setItem(KEY('text'), JSON.stringify('Hello UIC'))
    localStorage.setItem(KEY('analysis'), JSON.stringify(old))
    localStorage.setItem(KEY('decisions'), JSON.stringify({ c1: 'rejected', ghost: 'accepted' }))
    localStorage.setItem(KEY('revealed'), JSON.stringify(['brand', 'legal']))
    const { result } = renderHook(useAll, { wrapper })
    expect(result.current.text.analysis?.guidelines).toEqual([])
    expect(result.current.text.decisions).toEqual({ c1: 'rejected' })
    expect(result.current.text.currentText).toBe('Hello UIC')
    expect(result.current.text.currentScores?.brand).toBe(90)
    expect([...result.current.ui.revealed]).toEqual(['brand'])
  })
})

describe('races', () => {
  it('a reply that arrives after reset() does not repopulate chat or the analysis', async () => {
    const d = deferred<RefineResponse>()
    vi.mocked(refine).mockReturnValue(d.promise)
    const { result } = renderHook(useAll, { wrapper })
    act(() => result.current.text.setText('Hello there'))
    let p!: Promise<void>
    act(() => {
      p = result.current.text.sendChat('Make it shorter')
    })
    expect(result.current.text.chatPending).toBe(true)
    act(() => result.current.text.reset())
    expect(result.current.text.chatPending).toBe(false)
    await act(async () => {
      d.resolve({ reply: 'Done', analysis: analysisFor('Hello there', [], []) })
      await p
    })
    expect(result.current.text.chat).toEqual([])
    expect(result.current.text.analysis).toBeNull()
    expect(result.current.text.chatPending).toBe(false)
  })

  it('a reply that arrives after clearChat() is dropped and does not end a newer pending request', async () => {
    const first = deferred<RefineResponse>()
    const second = deferred<RefineResponse>()
    vi.mocked(refine).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result } = renderHook(useAll, { wrapper })
    let p1!: Promise<void>
    act(() => {
      p1 = result.current.text.sendChat('one')
    })
    act(() => result.current.text.clearChat())
    act(() => {
      void result.current.text.sendChat('two')
    })
    await act(async () => {
      first.resolve({ reply: 'late reply to one' })
      await p1
    })
    expect(result.current.text.chat.map((m) => m.content)).toEqual(['two'])
    expect(result.current.text.chatPending).toBe(true)
    await act(async () => second.resolve({ reply: 'reply to two' }))
    await waitFor(() => expect(result.current.text.chatPending).toBe(false))
    expect(result.current.text.chat.map((m) => m.content)).toEqual(['two', 'reply to two'])
  })

  it('a chat rewrite based on an older analysis does not overwrite a newer analysis', async () => {
    const d = deferred<RefineResponse>()
    vi.mocked(refine).mockReturnValue(d.promise)
    const { result } = renderHook(useAll, { wrapper })
    act(() => result.current.text.setText('First draft.'))
    await act(() => result.current.text.runAnalysis())
    let p!: Promise<void>
    act(() => {
      p = result.current.text.sendChat('Make it friendlier')
    })
    act(() => result.current.text.setText('Second draft.'))
    await act(() => result.current.text.runAnalysis())
    const newer = result.current.text.analysis
    expect(newer?.original).toBe('Second draft.')
    await act(async () => {
      d.resolve({ reply: 'Here you go', analysis: analysisFor('First draft.', [], [], { analysis_id: 'stale' }) })
      await p
    })
    expect(result.current.text.analysis).toBe(newer)
    expect(result.current.text.chat.at(-1)?.content).toBe('Here you go')
  })

  it('double sendChat in the same tick only sends once', async () => {
    vi.mocked(refine).mockResolvedValue({ reply: 'ok' })
    const { result } = renderHook(useAll, { wrapper })
    await act(async () => {
      await Promise.all([result.current.text.sendChat('a'), result.current.text.sendChat('b')])
    })
    expect(refine).toHaveBeenCalledTimes(1)
  })

  it('cancel then re-run: the cancelled response never lands, the new one does', async () => {
    const slow = deferred<AnalyzeResponse>()
    vi.mocked(analyze).mockReturnValueOnce(slow.promise)
    const { result } = renderHook(useAll, { wrapper })
    act(() => result.current.text.setText('Draft one'))
    act(() => {
      void result.current.text.runAnalysis()
    })
    act(() => result.current.text.cancelAnalysis())
    expect(result.current.text.status).toBe('idle')
    await act(() => result.current.text.runAnalysis())
    const fresh = result.current.text.analysis
    await act(async () => slow.resolve(analysisFor('Draft one', [], [], { analysis_id: 'cancelled' })))
    expect(result.current.text.analysis).toBe(fresh)
    expect(result.current.text.status).toBe('success')
  })

  it('cancelAnalysis does nothing when no analysis is running (keeps an error visible)', async () => {
    vi.mocked(analyze).mockRejectedValueOnce({ status: 503, message: 'down', retryable: true })
    const { result } = renderHook(useAll, { wrapper })
    act(() => result.current.text.setText('Draft'))
    await act(() => result.current.text.runAnalysis())
    expect(result.current.text.status).toBe('error')
    act(() => result.current.text.cancelAnalysis())
    expect(result.current.text.status).toBe('error')
  })
})

describe('isStale', () => {
  it('ignores ruleset order differences between the response and the selection', async () => {
    vi.mocked(analyze).mockImplementation(async (req) => ({ ...mockAnalyze(req), rulesets: [...req.rulesets].sort() }))
    const { result } = renderHook(useAll, { wrapper })
    act(() => result.current.text.setText('Hello UIC'))
    await act(() => result.current.text.runAnalysis())
    expect(result.current.text.isStale).toBe(false)
    act(() => result.current.rules.setAudience('Faculty'))
    expect(result.current.text.isStale).toBe(true)
    act(() => result.current.rules.setAudience('Students'))
    expect(result.current.text.isStale).toBe(false)
  })
})

describe('derived openIssues', () => {
  it('a change dropped as overlapping/out of range does not resolve its issue', () => {
    const a = analysisFor('Hello UIC', [chg('ok', 0, 5, 'Hi', ['i1']), chg('bad', 3, 99, 'X', ['i2'])], [iss('i1'), iss('i2')])
    localStorage.setItem(KEY('analysis'), JSON.stringify(a))
    const { result } = renderHook(useAll, { wrapper })
    expect(result.current.text.currentText).toBe('Hi UIC')
    expect(result.current.text.openIssues.map((i) => i.issue_id)).toEqual(['i2'])
  })

  it('an issue addressed by several changes stays open until all of them are applied; document issues stay listed', () => {
    const a = analysisFor(
      'aa bb',
      [chg('c1', 0, 2, 'A', ['i1', 'doc']), chg('c2', 3, 5, 'B', ['i1']), chg('c3', 2, 2, '', [])],
      [iss('i1'), iss('doc', { scope: 'document', ruleset: 'reading_level' })],
    )
    localStorage.setItem(KEY('analysis'), JSON.stringify(a))
    const { result } = renderHook(useAll, { wrapper })
    expect(result.current.text.openIssues).toEqual([])
    act(() => result.current.text.setDecision('c2', 'rejected'))
    expect(result.current.text.currentText).toBe('A bb')
    expect(result.current.text.openIssues.map((i) => i.issue_id)).toEqual(['i1'])
    expect(result.current.text.currentScores?.total_issues).toBe(1)
  })
})

describe('UI state', () => {
  it('renders without a provider error after corrupt revealed state', () => {
    localStorage.setItem(KEY('revealed'), '{"a":1}')
    expect(() => render(<UIProvider>ok</UIProvider>)).not.toThrow()
  })
})

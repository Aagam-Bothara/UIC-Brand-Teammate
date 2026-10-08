import axios, { AxiosError, type AxiosResponse } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyze, toApiError, withRetry } from '../api'

const httpError = (status: number | null, data: unknown = {}, code?: string) =>
  new AxiosError('Request failed', code ?? (status ? 'ERR_BAD_RESPONSE' : 'ERR_NETWORK'), undefined, undefined,
    status === null ? undefined : ({ status, data, statusText: '', headers: {}, config: {} } as unknown as AxiosResponse))

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('toApiError', () => {
  it('gives friendly messages for 4xx instead of "Request failed with status code 400"', () => {
    for (const s of [400, 401, 403, 404, 409, 413, 422, 429]) {
      const e = toApiError(httpError(s))
      expect(e.status).toBe(s)
      expect(e.message).not.toMatch(/request failed|status code/i)
      expect(e.retryable).toBe(s === 429)
    }
    expect(toApiError(httpError(413)).message).toMatch(/too long/i)
    expect(toApiError(httpError(400, { detail: 'Text is empty.' })).message).toBe('Text is empty.')
    expect(toApiError(httpError(400, { detail: { message: 'Pick an audience.' } })).message).toBe('Pick an audience.')
  })

  it('does not show raw server detail for 5xx, and explains timeouts', () => {
    expect(toApiError(httpError(500, { detail: 'KeyError: bedrock' })).message).not.toMatch(/KeyError/)
    expect(toApiError(httpError(null, undefined, 'ECONNABORTED')).message).toMatch(/too long/i)
    expect(toApiError(httpError(null)).message).toMatch(/can’t reach/i)
  })

  it('passes an ApiError through and hides raw JS errors', () => {
    const api = { status: 418, message: 'Teapot', retryable: false }
    expect(toApiError(api)).toEqual(api)
    expect(toApiError(new TypeError("Cannot read properties of undefined (reading 'x')")).message).not.toMatch(/undefined/)
    expect(toApiError('boom').retryable).toBe(false)
  })

  it('marks cancellations as cancelled and not retryable', () => {
    const e = toApiError(new axios.CanceledError())
    expect(e).toMatchObject({ retryable: false, cancelled: true })
    expect(toApiError(new DOMException('aborted', 'AbortError'))).toMatchObject({ cancelled: true })
  })
})

describe('withRetry', () => {
  it('retries 5xx / network errors 3 times with growing backoff, then throws', async () => {
    vi.useFakeTimers()
    const fn = vi.fn().mockRejectedValue(httpError(503))
    const p = withRetry(fn)
    const done = expect(p).rejects.toMatchObject({ status: 503, retryable: true })
    await vi.advanceTimersByTimeAsync(20_000)
    await done
    expect(fn).toHaveBeenCalledTimes(4)
  })

  it('never retries 4xx', async () => {
    const fn = vi.fn().mockRejectedValue(httpError(422))
    await expect(withRetry(fn)).rejects.toMatchObject({ status: 422 })
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('does not retry a cancelled request', async () => {
    const fn = vi.fn().mockRejectedValue(new axios.CanceledError())
    await expect(withRetry(fn)).rejects.toMatchObject({ cancelled: true })
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('stops waiting as soon as the signal aborts during backoff', async () => {
    vi.useFakeTimers()
    const ctrl = new AbortController()
    const fn = vi.fn().mockRejectedValue(httpError(null))
    const p = withRetry(fn, 3, ctrl.signal)
    const done = expect(p).rejects.toMatchObject({ cancelled: true })
    await vi.advanceTimersByTimeAsync(10)
    ctrl.abort()
    await vi.advanceTimersByTimeAsync(0)
    await done
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('does not even start when already aborted', async () => {
    const ctrl = new AbortController()
    ctrl.abort()
    const fn = vi.fn()
    await expect(withRetry(fn, 3, ctrl.signal)).rejects.toMatchObject({ cancelled: true })
    expect(fn).not.toHaveBeenCalled()
  })
})

describe('analyze', () => {
  const req = { text: 'Hello UIC', audience: 'Students', channel: 'Email', rulesets: ['brand'] } as const

  it('mock path honours an AbortSignal that is already aborted', async () => {
    const ctrl = new AbortController()
    ctrl.abort()
    await expect(analyze({ ...req, rulesets: [...req.rulesets] }, ctrl.signal)).rejects.toMatchObject({ cancelled: true })
  })

  it('real path normalizes WS2 vocab in the response (status, audience) and rejects garbage', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.resetModules()
    const api = await import('../api')
    const post = vi.spyOn(api.backend, 'post')
    post.mockResolvedValueOnce({
      data: {
        analysis_id: 'x', original: 'Hello UIC', rewritten: 'Hello UIC', changes: [], issues: [], guidelines: [],
        audience: 'students', channel: 'email', rulesets: ['brand'], model_used: 'haiku', latency_ms: 5,
        scores: { brand: 80, accessibility: 100, total_issues: 3, status: 'Minor Revisions', reading_level: { grade: 3, target: 8, audience: 'students' } },
      },
    })
    const res = await api.analyze({ ...req, rulesets: [...req.rulesets] })
    expect(res.scores.status).toBe('Minor Revisions Needed')
    expect(res.audience).toBe('Students')
    expect(res.channel).toBe('Email')
    post.mockResolvedValueOnce({ data: '<html>gateway error</html>' })
    await expect(api.analyze({ ...req, rulesets: [...req.rulesets] })).rejects.toMatchObject({ retryable: false })
  })
})

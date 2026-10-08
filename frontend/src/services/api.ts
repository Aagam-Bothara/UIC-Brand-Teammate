/**
 * API client (Task 4.2 / 4.11).
 *
 * - Backend (`VITE_API_BASE_URL`): /api/analyze, /api/llm/refine, /api/rules, /api/audiences
 *   (/api/rules and /api/audiences are Workstream 2's shapes, mapped by ws2Adapter.ts).
 *   While `VITE_USE_MOCKS` is not "false", these use services/mockData.ts.
 * - RAG (`VITE_RAG_API_URL`, Workstream 1 — deployed): /api/rag/context, /api/rag/retrieve.
 *   Used even in mock mode so guideline excerpts are real; falls back to mock excerpts on failure.
 * - SPEC NFR-3: 3 retries with exponential backoff on network errors, 429 and 5xx.
 */
import axios, { AxiosError, type AxiosInstance } from 'axios'
import { AUDIENCES, RULESET_ORDER, RULESETS } from '../config/rulesets'
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiError,
  AudienceInfo,
  GuidelineChunk,
  RefineRequest,
  RefineResponse,
  RulesetInfo,
} from '../types/api'
import { sanitizeAnalysis } from '../lib/sanitize'
import { MOCK_GUIDELINES, mockAnalyze, mockRefine } from './mockData'
import { adaptAudiences, adaptRules } from './ws2Adapter'

const env = import.meta.env
export const USE_MOCKS = env.VITE_USE_MOCKS !== 'false'
export const API_BASE_URL: string = env.VITE_API_BASE_URL ?? ''
export const RAG_API_URL: string = env.VITE_RAG_API_URL ?? ''

// Slightly above API Gateway's 29 s integration limit, so its 504 arrives before our own timeout.
export const backend: AxiosInstance = axios.create({ baseURL: API_BASE_URL, timeout: 32000 })
export const rag: AxiosInstance = axios.create({ baseURL: RAG_API_URL || API_BASE_URL, timeout: 15000 })

const MAX_RETRIES = 3
const BASE_DELAY_MS = 400

export const CANCELLED: ApiError = Object.freeze({ status: null, message: 'Request cancelled.', retryable: false, cancelled: true })
const cancelled = (): ApiError => ({ ...CANCELLED })

/** Resolves after `ms`, or rejects with a cancellation as soon as `signal` aborts. */
const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(cancelled())
    const onAbort = () => {
      clearTimeout(t)
      reject(cancelled())
    }
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    signal?.addEventListener('abort', onAbort, { once: true })
  })

const isApiError = (v: unknown): v is ApiError =>
  typeof v === 'object' && v !== null && typeof (v as ApiError).message === 'string' && typeof (v as ApiError).retryable === 'boolean'

const GENERIC = 'Something went wrong. Please try again.'

function httpMessage(status: number): string {
  if (status === 413) return 'Your draft is too long for the service. Try analyzing one section at a time.'
  if (status === 429) return 'The service is busy right now. Please wait a moment and try again.'
  if (status === 400 || status === 422) return 'Some of the input is invalid. Please check your text and settings.'
  if (status === 401 || status === 403) return 'You don’t have access to this service. Try reloading the page.'
  if (status === 404) return 'The service isn’t available right now. Please try again later.'
  if (status >= 500) return 'The service is having trouble right now. Please try again in a moment.'
  return `The request couldn’t be completed (error ${status}). Please try again.`
}

export function toApiError(err: unknown): ApiError {
  if (axios.isCancel(err) || (err instanceof Error && err.name === 'AbortError') || (err instanceof DOMException && err.name === 'AbortError')) {
    return cancelled()
  }
  if (axios.isAxiosError(err)) {
    const e = err as AxiosError<{ detail?: unknown } | undefined>
    const status = e.response?.status ?? null
    const data = e.response?.data
    const detail = typeof data === 'object' && data !== null ? data.detail : undefined
    let message: string
    if (status === null) {
      message = e.code === 'ECONNABORTED' || e.code === 'ETIMEDOUT'
        ? 'The request took too long. Please try again.'
        : 'Can’t reach the server. Check your connection and try again.'
    } else if (status < 500 && typeof detail === 'string' && detail.trim()) {
      // FastAPI HTTPException detail strings are written for users; 5xx details are not.
      message = detail
    } else if (status < 500 && typeof detail === 'object' && detail !== null && typeof (detail as { message?: unknown }).message === 'string') {
      message = (detail as { message: string }).message
    } else {
      message = status === 504 ? 'The analysis took too long. Try a shorter draft or try again.' : httpMessage(status)
    }
    // Timeouts (ours or API Gateway's 504) are not retried: an LLM call that was too slow once will
    // likely be slow again, and retrying would leave the user waiting minutes.
    const timedOut = e.code === 'ECONNABORTED' || e.code === 'ETIMEDOUT' || status === 504
    return { status, message, retryable: !timedOut && (status === null || status === 429 || status >= 500) }
  }
  if (isApiError(err)) return err
  // Raw JS errors (TypeError, …) aren't meaningful to users; keep them in the console for developers.
  if (err !== undefined) console.error(err)
  return { status: null, message: GENERIC, retryable: false }
}

/** Run `fn`, retrying retryable failures with exponential backoff + jitter. Throws ApiError. Honors `signal`. */
export async function withRetry<T>(fn: () => Promise<T>, retries = MAX_RETRIES, signal?: AbortSignal): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    if (signal?.aborted) throw cancelled()
    try {
      return await fn()
    } catch (err) {
      if (signal?.aborted) throw cancelled()
      const apiErr = toApiError(err)
      if (!apiErr.retryable || attempt >= retries) throw apiErr
      await sleep(BASE_DELAY_MS * 2 ** attempt * (0.5 + Math.random()), signal)
    }
  }
}

const BAD_RESPONSE: ApiError = { status: null, message: 'The service sent back an unexpected response. Please try again.', retryable: false }

// ----------------------------------------------------------------------------- RAG (live)

export async function ragContext(
  req: Pick<AnalyzeRequest, 'text' | 'audience' | 'channel' | 'rulesets'>,
  topK = 6,
  signal?: AbortSignal,
): Promise<GuidelineChunk[]> {
  const { data } = await withRetry(
    () => rag.post<{ results: GuidelineChunk[] }>('/api/rag/context', { ...req, text: req.text.slice(0, 40000), top_k: topK }, { signal }),
    1,
    signal,
  )
  return data.results
}

export async function ragRetrieve(query: string, audience?: string, topK = 3, signal?: AbortSignal): Promise<GuidelineChunk[]> {
  const { data } = await withRetry(
    () => rag.post<{ results: GuidelineChunk[] }>('/api/rag/retrieve', { query: query.slice(0, 1000), audience, top_k: topK }, { signal }),
    1,
    signal,
  )
  return data.results
}

// ----------------------------------------------------------------------------- backend

/**
 * LLM-backed calls are not retried by the browser: the backend already retries Bedrock within its time
 * budget, and a Lambda timeout (503 from API Gateway) retried here would double the wait to ~1 minute.
 */
const LLM_RETRIES = 0

export async function analyze(req: AnalyzeRequest, signal?: AbortSignal): Promise<AnalyzeResponse> {
  if (USE_MOCKS) {
    if (signal?.aborted) throw cancelled()
    const guidelines = await ragContext(req, 6, signal).catch(() => MOCK_GUIDELINES)
    if (signal?.aborted) throw cancelled()
    return mockAnalyze(req, guidelines)
  }
  const { data } = await withRetry(() => backend.post<unknown>('/api/analyze', req, { signal }), LLM_RETRIES, signal)
  const result = sanitizeAnalysis(data)
  if (!result) throw { ...BAD_RESPONSE }
  return result
}

export async function refine(req: RefineRequest, signal?: AbortSignal): Promise<RefineResponse> {
  if (USE_MOCKS) {
    if (signal?.aborted) throw cancelled()
    const guidelines = await ragRetrieve(req.message, req.audience, 3, signal).catch(() => [] as GuidelineChunk[])
    if (signal?.aborted) throw cancelled()
    return mockRefine(req, guidelines)
  }
  const { data } = await withRetry(() => backend.post<unknown>('/api/llm/refine', req, { signal }), LLM_RETRIES, signal)
  const d = (typeof data === 'object' && data !== null ? data : {}) as Record<string, unknown>
  if (typeof d.reply !== 'string') throw { ...BAD_RESPONSE }
  return {
    reply: d.reply,
    analysis: d.analysis ? sanitizeAnalysis(d.analysis) : null,
    guidelines: Array.isArray(d.guidelines) ? (d.guidelines as GuidelineChunk[]) : [],
  }
}

export async function getRules(): Promise<RulesetInfo[]> {
  const fallback = RULESET_ORDER.map((id) => RULESETS[id])
  if (USE_MOCKS) return fallback
  try {
    const { data } = await withRetry(() => backend.get<unknown>('/api/rules'), 1)
    return adaptRules(data)
  } catch {
    return fallback
  }
}

export async function getAudiences(): Promise<AudienceInfo[]> {
  if (USE_MOCKS) return AUDIENCES
  try {
    const { data } = await withRetry(() => backend.get<unknown>('/api/audiences'), 1)
    return adaptAudiences(data)
  } catch {
    return AUDIENCES
  }
}

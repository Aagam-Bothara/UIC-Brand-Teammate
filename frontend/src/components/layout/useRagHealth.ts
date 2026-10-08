import { useEffect, useState } from 'react'
import { rag } from '../../services/api'

export type RagHealth = 'checking' | 'ok' | 'degraded' | 'unavailable'

/** Ping the guidelines (RAG) service once on load. Never throws; failures read as 'unavailable'. */
export function useRagHealth(): RagHealth {
  const [health, setHealth] = useState<RagHealth>('checking')
  useEffect(() => {
    const ctrl = new AbortController()
    rag
      .get<{ status?: string } | string>('/api/rag/health', { signal: ctrl.signal, timeout: 8000 })
      .then(({ data }) => {
        if (ctrl.signal.aborted) return
        const status = typeof data === 'object' && data ? data.status : undefined
        setHealth(status === 'ok' ? 'ok' : status === 'degraded' ? 'degraded' : 'unavailable')
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setHealth('unavailable')
      })
    return () => ctrl.abort()
  }, [])
  return health
}

import { USE_MOCKS } from '../../services/api'
import Tip from './Tip'
import { useRagHealth } from './useRagHealth'

/**
 * One tiny status dot (with a tooltip) for the data sources: mock vs. live analysis, plus the
 * guidelines (RAG) service when it answered. Amber = sample data, green = live.
 */
export default function ConnectionStatus({ className = '' }: { className?: string }) {
  const health = useRagHealth()
  const lines = [USE_MOCKS ? 'Mock data' : 'Live']
  if (health === 'ok') lines.push('Guidelines: live')
  if (health === 'degraded') lines.push('Guidelines: limited')
  const dot = USE_MOCKS ? 'bg-amber-500' : health === 'degraded' ? 'bg-uic-steel/40' : 'bg-uic-green'
  const detail = USE_MOCKS ? 'Analysis uses sample data while the backend is being connected.' : 'Analysis runs on the live backend.'

  return (
    <Tip text={<>{lines.join(' · ')}<span className="block font-normal text-white/75">{detail}</span></>}>
      <span
        role="group"
        aria-label="Connection status"
        tabIndex={0}
        className={`grid size-6 shrink-0 place-items-center rounded-full ${className}`}
      >
        <span aria-hidden="true" className={`size-2 rounded-full ${dot} ring-2 ring-white`} />
        {lines.map((l) => (
          <span key={l} className="sr-only">
            {l}
          </span>
        ))}
      </span>
    </Tip>
  )
}

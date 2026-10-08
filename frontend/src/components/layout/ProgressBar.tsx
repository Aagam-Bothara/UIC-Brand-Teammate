import { useText } from '../../context/TextContext'
import './layout.css'

/** Slim indeterminate bar while an analysis runs: top of the viewport on small screens, under the sticky header on desktop. */
export default function ProgressBar() {
  const { status } = useText()
  const loading = status === 'loading'
  return (
    <div
      aria-hidden={!loading}
      className={`pointer-events-none fixed inset-x-0 top-0 z-[70] h-[3px] overflow-hidden lg:absolute lg:top-auto lg:bottom-0 lg:translate-y-full transition-opacity duration-300 ${loading ? 'opacity-100' : 'opacity-0'}`}
    >
      {loading && (
        <div role="progressbar" aria-label="Analyzing your draft" aria-valuetext="Analyzing…" className="h-full w-full bg-uic-navy/10">
          <div className="uic-progress-indicator h-full w-1/4 rounded-full bg-linear-to-r from-uic-chicago-blue via-uic-navy to-uic-red" />
        </div>
      )}
    </div>
  )
}

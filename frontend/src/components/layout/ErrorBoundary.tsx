import { RotateCw, TriangleAlert } from 'lucide-react'
import { Component, type ReactNode } from 'react'
import { clearAppData } from './appData'
import { btnPrimary, btnSecondary } from './ui'

interface Props {
  children: ReactNode
  /** `page` replaces the whole app; `section` replaces one panel and offers "Try again". */
  variant?: 'page' | 'section'
  /** Panel name for the section fallback, e.g. "the comparison view". */
  label?: string
  /** Injectable for tests; defaults to a full page reload. */
  onReload?: () => void
}

interface State {
  error: Error | null
}

const reloadPage = () => window.location.reload()

/** Task 4.10: friendly fallback instead of a blank screen when rendering fails. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  private reload = () => (this.props.onReload ?? reloadPage)()

  private resetAppData = () => {
    clearAppData()
    this.reload()
  }

  private retry = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return this.props.variant === 'section' ? this.renderSection() : this.renderPage(error)
  }

  private renderSection() {
    return (
      <section
        role="alert"
        className="rounded-2xl border border-dashed border-uic-red/30 bg-white p-5 text-sm shadow-sm sm:p-6"
      >
        <div className="flex items-start gap-3">
          <TriangleAlert size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-uic-red" />
          <div className="min-w-0">
            <p className="font-semibold text-uic-navy">
              {this.props.label ? `We couldn’t show ${this.props.label}.` : 'This panel couldn’t load.'}
            </p>
            <p className="mt-1 text-uic-steel/80">The rest of the app still works. Try again, or reload the page.</p>
            <button type="button" onClick={this.retry} className={`${btnSecondary} mt-3`}>
              <RotateCw size={16} aria-hidden="true" />
              Try again
            </button>
          </div>
        </div>
      </section>
    )
  }

  private renderPage(error: Error) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-uic-expo p-4">
        <div className="fixed inset-x-0 top-0 h-1 bg-uic-red" aria-hidden="true" />
        <main
          role="alert"
          className="w-full max-w-md rounded-2xl border border-black/5 bg-white p-6 text-center shadow-sm sm:p-8"
        >
          <span aria-hidden="true" className="mx-auto grid size-12 place-items-center rounded-2xl bg-uic-red/10 text-uic-red">
            <TriangleAlert size={22} />
          </span>
          <h1 className="mt-4 text-xl font-semibold tracking-tight text-uic-navy">Something went wrong</h1>
          <p className="mt-2 text-sm leading-relaxed text-uic-steel/80">
            UIC Brand Teammate hit an unexpected problem. Your draft is saved in this browser, so reloading
            usually fixes it.
          </p>
          <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
            <button type="button" onClick={this.reload} className={btnPrimary}>
              <RotateCw size={16} aria-hidden="true" />
              Reload
            </button>
            <button type="button" onClick={this.resetAppData} className={`${btnSecondary} text-uic-red`}>
              Reset app data
            </button>
          </div>
          <p className="mt-3 text-xs text-uic-steel/75">
            “Reset app data” clears your saved draft, results and settings on this device.
          </p>
          <details className="mt-5 text-left text-xs text-uic-steel/75">
            <summary className="cursor-pointer select-none rounded font-medium">Technical details</summary>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-lg bg-uic-expo p-3 font-mono">
              {error.message || String(error)}
            </pre>
          </details>
        </main>
      </div>
    )
  }
}

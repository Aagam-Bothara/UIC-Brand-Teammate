import { LoaderCircle, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useText } from '../../context/TextContext'
import ComparisonView from '../ComparisonView'
import ComplianceDisplay from '../ComplianceDisplay'
import ExportButton from '../ExportButton'
import RulesetPanel from '../RulesetPanel'
import TextInput from '../TextInput'
import ChatDrawer from './ChatDrawer'
import ErrorBoundary from './ErrorBoundary'
import Footer from './Footer'
import Header from './Header'
import HowItWorks from './HowItWorks'
import Toaster from './Toaster'
import { prefersReducedMotion } from './ui'

function Panel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ErrorBoundary variant="section" label={label}>
      {children}
    </ErrorBoundary>
  )
}

function ResultsStatus() {
  const { status, isStale } = useText()
  if (status === 'loading')
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-uic-navy/[0.06] px-2.5 py-0.5 text-xs font-medium text-uic-navy">
        <LoaderCircle size={12} aria-hidden="true" className="animate-spin" />
        Analyzing…
      </span>
    )
  if (isStale)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-600/20">
        <RefreshCw size={12} aria-hidden="true" />
        Draft changed — analyze again to update
      </span>
    )
  return null
}

/** True when `el` already sits comfortably in view (below a sticky header, in the upper half). */
function isComfortablyInView(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect()
  return r.top >= 80 && r.bottom <= window.innerHeight * 0.6
}

/** Task 4.10 main layout: header, draft + settings, results, chat drawer, toasts. */
export default function AppShell() {
  const { analysis, status } = useText()
  const [howOpen, setHowOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null)
  const prevStatus = useRef(status)
  const hasAnalysis = analysis !== null

  // After a successful analysis, bring the results into view (unless they already are) and move focus to their heading.
  useEffect(() => {
    if (prevStatus.current === 'loading' && status === 'success') {
      const heading = resultsHeadingRef.current
      if (heading && !isComfortablyInView(heading)) {
        heading.scrollIntoView?.({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' })
      }
      heading?.focus({ preventScroll: true })
    }
    prevStatus.current = status
  }, [status])

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-xl focus:bg-uic-navy focus:px-4 focus:py-2.5 focus:text-sm focus:font-medium focus:text-white focus:shadow-lg"
      >
        Skip to main content
      </a>

      <Header onHowItWorks={() => setHowOpen(true)} onAskEditor={() => setChatOpen(true)} chatOpen={chatOpen} />

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1440px] flex-1 px-4 pb-10 pt-5 outline-none sm:px-6 sm:pt-8 lg:px-8">
        <h1 className="sr-only">UIC Brand Teammate</h1>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-8">
          {/* Draft + settings */}
          <div
            data-region="input"
            className={`flex min-w-0 flex-col gap-6 ${hasAnalysis ? 'lg:col-span-5 xl:col-span-4 2xl:col-span-3' : 'lg:col-span-7'}`}
          >
            <Panel label="the text editor">
              <TextInput />
            </Panel>
            <Panel label="the ruleset settings">
              <RulesetPanel />
            </Panel>
          </div>

          {/* Results */}
          <section
            aria-labelledby="results-title"
            aria-busy={status === 'loading'}
            className={`flex min-w-0 flex-col gap-3 ${hasAnalysis ? 'lg:col-span-7 xl:col-span-8 2xl:col-span-9' : 'lg:col-span-5'}`}
          >
            <div className="flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                <h2
                  id="results-title"
                  ref={resultsHeadingRef}
                  tabIndex={-1}
                  className="scroll-mt-24 text-[15px] font-semibold tracking-tight text-uic-navy outline-none"
                >
                  Results
                </h2>
                <ResultsStatus />
              </div>
              {hasAnalysis && (
                <Panel label="the export options">
                  <ExportButton />
                </Panel>
              )}
            </div>
            <div
              className={`grid items-start gap-6 ${hasAnalysis ? '2xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]' : ''}`}
            >
              <div className="min-w-0">
                <Panel label="the comparison view">
                  <ComparisonView />
                </Panel>
              </div>
              <div className={`min-w-0 ${hasAnalysis ? '2xl:sticky 2xl:top-24' : ''}`}>
                <Panel label="the compliance scores">
                  <ComplianceDisplay />
                </Panel>
              </div>
            </div>
          </section>
        </div>
      </main>

      <Footer />
      <ChatDrawer open={chatOpen} onOpenChange={setChatOpen} />
      <HowItWorks open={howOpen} onClose={() => setHowOpen(false)} />
      <Toaster />
    </div>
  )
}

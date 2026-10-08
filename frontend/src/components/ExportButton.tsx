import { Check, ChevronDown, Copy, Download, FileDown, FileText, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { useRulesets } from '../context/RulesetContext'
import { useText } from '../context/TextContext'
import { useUI } from '../context/UIContext'
import { copyText, downloadBlob, reportFilename, textFilename } from './export/clipboard'
import { buildReportData, buildReportPdf } from './export/pdfReport'

const TRIGGER =
  'inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-uic-navy py-2.5 pr-3 pl-4 text-sm font-medium text-white shadow-sm transition duration-150 hover:bg-uic-navy/90 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:hover:bg-uic-navy'
const ITEM =
  'flex min-h-10 w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm font-medium text-uic-navy outline-none transition hover:bg-black/[0.04] focus-visible:bg-black/[0.05]'

type ExportAction = 'copy' | 'pdf' | 'txt'

/**
 * Task 4.9 — export the improved text (copy / .txt) or a PDF compliance report (FR-12), behind one
 * "Export" menu button (WAI-ARIA menu button: arrows / Home / End move, Esc or Tab closes).
 */
export default function ExportButton() {
  const { analysis, status, currentText, currentScores, openIssues, decisions } = useText()
  const { revealed, notify } = useUI()
  const { rulesetById } = useRulesets()
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const wrapRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  /** Which item to focus when the menu opens. */
  const focusOnOpen = useRef<'first' | 'last'>('first')
  const reasonId = useId()
  const menuId = useId()

  useEffect(() => () => clearTimeout(copiedTimer.current), [])

  const ready = !!analysis && !!currentScores && status !== 'loading'
  const disabled = !ready
  const unavailable = disabled || pdfBusy

  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])

  // Focus an item when the menu opens; close on a click outside.
  useEffect(() => {
    if (!open) return
    const list = items()
    ;(focusOnOpen.current === 'last' ? list[list.length - 1] : list[0])?.focus()
    const onPointer = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    return () => document.removeEventListener('pointerdown', onPointer)
  }, [open])

  // Close if exporting becomes unavailable (e.g. a new analysis starts).
  useEffect(() => {
    if (unavailable) setOpen(false)
  }, [unavailable])

  const close = (refocus = true) => {
    setOpen(false)
    if (refocus) triggerRef.current?.focus()
  }

  const onCopy = async () => {
    const ok = await copyText(currentText)
    if (ok) {
      setCopied(true)
      clearTimeout(copiedTimer.current)
      copiedTimer.current = setTimeout(() => setCopied(false), 2000)
      notify('Improved text copied to clipboard', 'success')
    } else {
      notify('Couldn’t copy automatically. Select the text and press Ctrl+C (⌘C on Mac).', 'error')
    }
  }

  const onPdf = async () => {
    if (!analysis || !currentScores) return
    setPdfBusy(true)
    try {
      const data = buildReportData({ analysis, currentText, currentScores, openIssues, revealed, decisions, rulesetById })
      const doc = await buildReportPdf(data)
      downloadBlob(doc.output('blob'), reportFilename(data.generatedAt))
      notify('PDF report downloaded', 'success')
    } catch {
      notify('Couldn’t create the PDF report. Please try again.', 'error')
    } finally {
      setPdfBusy(false)
    }
  }

  const onTxt = () => {
    downloadBlob(new Blob([currentText], { type: 'text/plain;charset=utf-8' }), textFilename())
    notify('Text file downloaded', 'success')
  }

  const run = (action: ExportAction) => {
    close()
    if (action === 'copy') void onCopy()
    else if (action === 'pdf') void onPdf()
    else onTxt()
  }

  const openMenu = (focus: 'first' | 'last') => {
    if (unavailable) return
    focusOnOpen.current = focus
    setOpen(true)
  }

  const onTriggerKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      openMenu(e.key === 'ArrowUp' ? 'last' : 'first')
    }
  }

  const onMenuKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const list = items()
    const i = list.indexOf(document.activeElement as HTMLElement)
    const move = (to: number) => {
      e.preventDefault()
      list[(to + list.length) % list.length]?.focus()
    }
    if (e.key === 'ArrowDown') move(i + 1)
    else if (e.key === 'ArrowUp') move(i - 1)
    else if (e.key === 'Home') move(0)
    else if (e.key === 'End') move(list.length - 1)
    else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      close()
    } else if (e.key === 'Tab') close(false)
  }

  const label = pdfBusy ? 'Preparing report…' : copied ? 'Copied' : 'Export'

  return (
    <div ref={wrapRef} className="group relative inline-flex">
      <span id={reasonId} className="sr-only">
        Run an analysis first to export.
      </span>
      <button
        ref={triggerRef}
        type="button"
        className={TRIGGER}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-disabled={unavailable || undefined}
        aria-busy={pdfBusy || undefined}
        aria-describedby={disabled ? reasonId : undefined}
        onClick={() => (open ? close(false) : openMenu('first'))}
        onKeyDown={onTriggerKeyDown}
      >
        {pdfBusy ? (
          <LoaderCircle size={16} aria-hidden="true" className="animate-spin" />
        ) : copied ? (
          <Check size={16} aria-hidden="true" />
        ) : (
          <Download size={16} aria-hidden="true" />
        )}
        {label}
        <ChevronDown size={16} aria-hidden="true" className={`opacity-80 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      {disabled && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute top-full right-0 z-20 mt-2 hidden w-max max-w-[min(14rem,calc(100vw-2rem))] rounded-lg bg-uic-navy px-2.5 py-1.5 text-xs text-white shadow-md transition duration-150 group-focus-within:block group-hover:block starting:opacity-0"
        >
          Run an analysis first to export
        </span>
      )}
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Export"
          onKeyDown={onMenuKeyDown}
          className="absolute top-full right-0 z-30 mt-2 w-60 rounded-xl border border-black/10 bg-white p-1.5 shadow-xl ring-1 ring-black/5"
        >
          <button type="button" role="menuitem" tabIndex={-1} className={ITEM} onClick={() => run('copy')}>
            <Copy size={16} aria-hidden="true" />
            Copy text
          </button>
          <button type="button" role="menuitem" tabIndex={-1} className={ITEM} onClick={() => run('pdf')}>
            <FileDown size={16} aria-hidden="true" />
            PDF report
          </button>
          <button type="button" role="menuitem" tabIndex={-1} className={ITEM} onClick={() => run('txt')}>
            <FileText size={16} aria-hidden="true" />
            Text file (.txt)
          </button>
        </div>
      )}
    </div>
  )
}

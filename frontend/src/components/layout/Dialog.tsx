import { X } from 'lucide-react'
import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import './layout.css'
import { useFocusTrap } from './useFocusTrap'

export interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  /** Decorative icon shown beside the title. */
  icon?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  /** CSS selector (inside the dialog) for the element focused on open. */
  initialFocus?: string
}

const WIDTH = { sm: 'sm:max-w-md', md: 'sm:max-w-lg', lg: 'sm:max-w-2xl' } as const

/** Accessible modal dialog: focus trap, Esc / backdrop to close, focus restored on close. */
export default function Dialog(props: DialogProps) {
  if (!props.open) return null
  return createPortal(<DialogPanel {...props} />, document.body)
}

function DialogPanel({ onClose, title, description, icon, children, footer, size = 'sm', initialFocus }: DialogProps) {
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const descId = useId()
  useFocusTrap(ref, true, {
    onEscape: onClose,
    lockScroll: true,
    initialFocus: initialFocus ? (el) => el.querySelector<HTMLElement>(initialFocus) : undefined,
  })

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center p-3 sm:items-center sm:p-6">
      <div aria-hidden="true" className="uic-fade-in absolute inset-0 bg-uic-navy/40 backdrop-blur-[2px]" onClick={onClose} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={`uic-pop-in relative flex max-h-[min(90dvh,760px)] w-full flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-black/5 outline-none ${WIDTH[size]}`}
      >
        <div className="flex items-start gap-3 px-5 pt-5 sm:px-6 sm:pt-6">
          {icon && (
            <span aria-hidden="true" className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-xl bg-uic-navy/5 text-uic-navy">
              {icon}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-semibold tracking-tight text-uic-navy">
              {title}
            </h2>
            {description && (
              <div id={descId} className="mt-1 text-sm leading-relaxed text-uic-steel/80">
                {description}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="-mr-2 -mt-1 grid size-10 shrink-0 place-items-center rounded-xl text-uic-steel/70 transition hover:bg-black/[0.04] hover:text-uic-navy"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {children && <div className="min-h-0 overflow-y-auto px-5 pt-4 sm:px-6">{children}</div>}
        {footer && (
          <div className="mt-5 flex flex-col-reverse gap-2 border-t border-black/5 bg-uic-expo/50 px-5 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-6">
            {footer}
          </div>
        )}
        {!footer && <div className="h-5 sm:h-6" />}
      </div>
    </div>
  )
}

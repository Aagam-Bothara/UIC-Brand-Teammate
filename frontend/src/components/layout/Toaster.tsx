import { CircleAlert, CircleCheck, Info, X } from 'lucide-react'
import { useUI, type Toast } from '../../context/UIContext'
import './layout.css'

const TONES: Record<Toast['tone'], { icon: typeof Info; iconClass: string; bar: string; label: string }> = {
  success: { icon: CircleCheck, iconClass: 'text-uic-green', bar: 'bg-uic-green', label: 'Success' },
  error: { icon: CircleAlert, iconClass: 'text-uic-red', bar: 'bg-uic-red', label: 'Error' },
  info: { icon: Info, iconClass: 'text-uic-navy', bar: 'bg-uic-navy', label: 'Notice' },
}

/** Renders useUI().toasts, bottom-center: above the floating chat launcher below lg (it is docked in the header from lg up). */
export default function Toaster() {
  const { toasts, dismissToast } = useUI()
  return (
    <section aria-label="Notifications" className="pointer-events-none fixed inset-x-0 bottom-24 z-[90] px-4 lg:bottom-6">
      <ol aria-live="polite" aria-relevant="additions text" className="mx-auto flex max-w-md flex-col items-stretch gap-2">
        {toasts.map((t) => {
          const tone = TONES[t.tone]
          const Icon = tone.icon
          return (
            <li
              key={t.id}
              className="uic-pop-in pointer-events-auto relative flex items-start gap-3 overflow-hidden rounded-xl bg-white py-3 pl-4 pr-2 text-sm shadow-lg ring-1 ring-black/5"
            >
              <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-1 ${tone.bar}`} />
              <Icon size={18} aria-hidden="true" className={`mt-0.5 shrink-0 ${tone.iconClass}`} />
              <p className="min-w-0 flex-1 py-0.5 leading-snug text-uic-steel">
                <span className="sr-only">{tone.label}: </span>
                {t.message}
              </p>
              <button
                type="button"
                onClick={() => dismissToast(t.id)}
                aria-label="Dismiss notification"
                className="-my-1 grid size-8 shrink-0 place-items-center rounded-lg text-uic-steel/60 transition hover:bg-black/[0.04] hover:text-uic-navy"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

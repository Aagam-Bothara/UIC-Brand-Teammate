import { ExternalLink, MessageSquareText, Sparkles } from 'lucide-react'
import Dialog from './Dialog'
import { STEPS } from './steps'
import { btnPrimary } from './ui'

export default function HowItWorks({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="md"
      icon={<Sparkles size={18} />}
      title="How it works"
      description="UIC Brand Teammate turns a draft into on-brand, accessible copy in three steps."
      initialFocus="[data-autofocus]"
      footer={
        <>
          <a
            href="https://brand.uic.edu"
            target="_blank"
            rel="noreferrer"
            className="mr-auto inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl px-2 text-sm font-medium text-uic-navy underline-offset-4 hover:underline"
          >
            UIC brand guidelines
            <ExternalLink size={14} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          <button type="button" data-autofocus onClick={onClose} className={btnPrimary}>
            Got it
          </button>
        </>
      }
    >
      <ol className="space-y-3">
        {STEPS.map(({ icon: Icon, title, body }, i) => (
          <li key={title} className="flex gap-3.5 rounded-xl border border-black/5 bg-uic-expo/60 p-4">
            <span
              aria-hidden="true"
              className="grid size-9 shrink-0 place-items-center rounded-full bg-uic-navy text-sm font-semibold text-white"
            >
              {i + 1}
            </span>
            <div className="min-w-0">
              <h3 className="flex items-center gap-2 text-[15px] font-semibold text-uic-navy">
                <Icon size={16} aria-hidden="true" className="text-uic-navy/70" />
                {title}
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-uic-steel/85">{body}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-4 flex gap-2.5 rounded-xl bg-uic-beach px-4 py-3 text-sm leading-relaxed text-uic-steel">
        <MessageSquareText size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-uic-navy" />
        <span>
          <strong className="font-semibold text-uic-navy">Tip:</strong> open <em>Ask the editor</em> to request
          changes like “make it friendlier for first-year students” or to ask why an edit was made.
        </span>
      </p>
    </Dialog>
  )
}

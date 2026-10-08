import { CircleQuestionMark, Eraser, LoaderCircle, MessageSquareText, SquarePen } from 'lucide-react'
import { useState } from 'react'
import { useText } from '../../context/TextContext'
import { useUI } from '../../context/UIContext'
import ConnectionStatus from './ConnectionStatus'
import Dialog from './Dialog'
import ProgressBar from './ProgressBar'
import Tip from './Tip'
import { btnDanger, btnPrimary, btnSecondary, focusDraftInput } from './ui'

const iconBtn =
  'inline-flex size-10 items-center justify-center rounded-xl text-sm font-medium text-uic-navy transition duration-150 hover:bg-black/[0.04] active:scale-[0.98]'
import { BRAND_ASSETS } from './brand'

function NewDraftButton() {
  const { text, analysis, chat, reset } = useText()
  const { notify } = useUI()
  const [confirming, setConfirming] = useState(false)
  const hasWork = text.trim().length > 0 || analysis !== null || chat.length > 0

  const startOver = () => {
    reset()
    setConfirming(false)
    notify('Ready for a new draft', 'info')
    requestAnimationFrame(focusDraftInput)
  }

  return (
    <>
      <button
        type="button"
        onClick={() => (hasWork ? setConfirming(true) : startOver())}
        className={`${iconBtn} sm:w-auto sm:gap-2 sm:px-3`}
      >
        <SquarePen size={17} aria-hidden="true" />
        <span className="sr-only sm:not-sr-only">New draft</span>
      </button>
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        icon={<Eraser size={18} />}
        title="Start a new draft?"
        description="This clears your text, the rewrite and the chat. Your settings stay."
        initialFocus="[data-autofocus]"
        footer={
          <>
            <button type="button" data-autofocus onClick={() => setConfirming(false)} className={btnSecondary}>
              Keep editing
            </button>
            <button type="button" onClick={startOver} className={btnDanger}>
              Clear and start over
            </button>
          </>
        }
      />
    </>
  )
}

interface HeaderProps {
  onHowItWorks: () => void
  /** Opens the chat drawer (the header launcher is shown from lg up; below that the floating one is). */
  onAskEditor: () => void
  chatOpen: boolean
}

export default function Header({ onHowItWorks, onAskEditor, chatOpen }: HeaderProps) {
  const { chatPending } = useText()
  return (
    <header className="relative z-30 lg:sticky lg:top-0">
      <div className="border-b border-black/5 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-2.5 px-4 sm:gap-3 sm:px-6 lg:px-8">
          {/* Official marks (never recoloured/stretched): circle mark on phones, full logo from sm up. */}
          <img
            src={BRAND_ASSETS.circleMark}
            alt="University of Illinois Chicago"
            width={28}
            height={28}
            className="size-7 shrink-0 sm:hidden"
          />
          <img
            src={BRAND_ASSETS.logo}
            alt="University of Illinois Chicago"
            width={700}
            height={146}
            className="hidden h-[30px] w-auto shrink-0 sm:block"
          />
          <span aria-hidden="true" className="ml-1 hidden h-7 w-px shrink-0 bg-black/10 sm:block" />
          <p className="min-w-0 truncate text-[15px] font-semibold tracking-tight text-uic-navy sm:ml-1 sm:text-base">
            UIC Brand Teammate
          </p>
          <ConnectionStatus />
          <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-1.5">
            <Tip text="How it works" align="end">
              <button type="button" onClick={onHowItWorks} aria-label="How it works" className={iconBtn}>
                <CircleQuestionMark size={18} aria-hidden="true" />
              </button>
            </Tip>
            <NewDraftButton />
            <button
              type="button"
              onClick={onAskEditor}
              aria-expanded={chatOpen}
              aria-controls="chat-drawer"
              aria-haspopup="dialog"
              className={`${btnPrimary.replace('inline-flex', 'hidden lg:inline-flex')} ml-1`}
            >
              {chatPending ? (
                <LoaderCircle size={17} aria-hidden="true" className="animate-spin" />
              ) : (
                <MessageSquareText size={17} aria-hidden="true" />
              )}
              Ask the editor
            </button>
          </div>
        </div>
      </div>
      <ProgressBar />
    </header>
  )
}

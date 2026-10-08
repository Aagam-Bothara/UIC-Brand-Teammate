import { ClipboardPaste, Layers, SlidersHorizontal } from 'lucide-react'

/** The three-step flow shown in the hero and the How it works dialog. */
export const STEPS = [
  {
    icon: ClipboardPaste,
    title: 'Paste your draft',
    short: 'Paste your draft',
    body: 'Drop in an email, web page or social post — anything up to 5,000 words.',
  },
  {
    icon: SlidersHorizontal,
    title: 'Choose audience & rulesets',
    short: 'Pick audience & checks',
    body: 'Pick who you’re writing for (Students, Faculty or Staff), the channel, and which checks to run: Brand, Accessibility, Content, Reading Level and Audience Tone.',
  },
  {
    icon: Layers,
    title: 'Review, toggle & export',
    short: 'Review, toggle & export',
    body: 'Compare your original with the rewrite side by side. Toggle each ruleset to reveal its changes, accept or reject individual edits, then copy the clean text or download a PDF report.',
  },
] as const

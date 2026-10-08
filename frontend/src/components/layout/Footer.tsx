export default function Footer() {
  return (
    <footer>
      <p className="mx-auto max-w-[1440px] px-4 pb-24 pt-4 text-xs text-uic-steel/70 sm:px-6 lg:px-8 lg:pb-6">
        UIC Brand Teammate <span aria-hidden="true">·</span> Guidelines from{' '}
        <a
          href="https://brand.uic.edu"
          target="_blank"
          rel="noreferrer"
          className="font-medium text-uic-navy underline decoration-uic-navy/30 underline-offset-2 transition hover:decoration-uic-navy"
        >
          brand.uic.edu<span className="sr-only"> (opens in a new tab)</span>
        </a>{' '}
        <span aria-hidden="true">·</span> AI suggestions: always review before publishing.
      </p>
    </footer>
  )
}

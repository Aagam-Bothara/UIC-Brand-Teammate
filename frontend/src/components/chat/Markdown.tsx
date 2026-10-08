import { BookOpen, ExternalLink } from 'lucide-react'
import { Fragment, useMemo, type ReactNode } from 'react'
import { parseBlocks, type Block, type Inline } from './markdownParser'

/** Renders the safe Markdown subset from ./markdownParser.ts with React elements only. */
export default function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseBlocks(text), [text])
  return <div className="space-y-2.5 break-words">{renderBlocks(blocks, 'b')}</div>
}

function renderBlocks(blocks: Block[], key: string, inQuote = false): ReactNode[] {
  return blocks.map((block, i) => {
    const k = `${key}-${i}`
    switch (block.type) {
      case 'paragraph':
        return (
          <p key={k}>
            {block.lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {renderInline(line, `${k}-${j}`)}
              </Fragment>
            ))}
          </p>
        )
      case 'heading':
        return (
          <p key={k} className={inQuote ? 'text-xs font-semibold text-uic-navy/80' : 'font-semibold text-uic-navy'}>
            {renderInline(block.content, k)}
          </p>
        )
      case 'list': {
        const List = block.ordered ? 'ol' : 'ul'
        return (
          <List
            key={k}
            className={`space-y-1 pl-5 marker:text-uic-navy/60 ${block.ordered ? 'list-decimal' : 'list-disc'}`}
          >
            {block.items.map((item, j) => (
              <li key={j} className="pl-0.5">
                {renderInline(item, `${k}-${j}`)}
              </li>
            ))}
          </List>
        )
      }
      case 'quote':
        return inQuote ? (
          <blockquote key={k} className="border-l-2 border-black/10 pl-3">
            {renderBlocks(block.blocks, k, true)}
          </blockquote>
        ) : (
          <figure key={k} className="rounded-xl border border-uic-navy/10 bg-uic-expo/70 px-3.5 py-3">
            <figcaption className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-uic-navy/80">
              <BookOpen size={12} aria-hidden="true" />
              UIC guideline
            </figcaption>
            <blockquote className="space-y-2 border-l-2 border-uic-red pl-3 text-[13px] leading-relaxed text-uic-steel sm:text-sm">
              {renderBlocks(block.blocks, k, true)}
            </blockquote>
          </figure>
        )
    }
  })
}

function renderInline(nodes: Inline[], key: string): ReactNode[] {
  return nodes.map((node, i) => {
    const k = `${key}-${i}`
    switch (node.type) {
      case 'text':
        return <Fragment key={k}>{node.text}</Fragment>
      case 'strong':
        return (
          <strong key={k} className="font-semibold text-uic-navy">
            {renderInline(node.children, k)}
          </strong>
        )
      case 'em':
        return <em key={k}>{renderInline(node.children, k)}</em>
      case 'code':
        return (
          <code key={k} className="rounded bg-black/[0.05] px-1 py-0.5 font-mono text-[0.9em]">
            {node.text}
          </code>
        )
      case 'link':
        return (
          <a
            key={k}
            href={node.href}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-uic-navy underline decoration-uic-navy/30 underline-offset-2 transition-colors hover:decoration-uic-navy [overflow-wrap:anywhere]"
          >
            {renderInline(node.children, k)}
            <ExternalLink size={12} aria-hidden="true" className="ml-0.5 inline-block align-[-1px]" />
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        )
    }
  })
}

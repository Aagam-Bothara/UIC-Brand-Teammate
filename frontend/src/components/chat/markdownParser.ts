/**
 * A deliberately small Markdown subset for assistant chat replies (Task 4.8).
 *
 * Produces a plain data tree that <Markdown> renders with React elements only — no
 * dangerouslySetInnerHTML — so any HTML in a reply (e.g. `<script>`, `<img onerror>`) is
 * shown as literal text. Links are only ever created for http(s) URLs.
 *
 * Supported: paragraphs (single newlines become line breaks), `#` headings (rendered as a
 * bold line), `-`/`*`/`•` and `1.` lists, `>` blockquotes (nested Markdown inside), **bold**,
 * *italic*, `code`, [text](https://…) links and bare https:// URLs.
 */

export type Inline =
  | { type: 'text'; text: string }
  | { type: 'strong'; children: Inline[] }
  | { type: 'em'; children: Inline[] }
  | { type: 'code'; text: string }
  | { type: 'link'; href: string; children: Inline[] }

export type Block =
  | { type: 'paragraph'; lines: Inline[][] }
  | { type: 'heading'; content: Inline[] }
  | { type: 'list'; ordered: boolean; items: Inline[][] }
  | { type: 'quote'; blocks: Block[] }

const BULLET = /^\s{0,3}[-*•]\s+(.*)$/
const ORDERED = /^\s{0,3}\d{1,3}[.)]\s+(.*)$/
const QUOTE = /^\s{0,3}>\s?(.*)$/
const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/
const MAX_QUOTE_DEPTH = 3

const isBlank = (line: string) => line.trim() === ''
const isBlockStart = (line: string) => BULLET.test(line) || ORDERED.test(line) || QUOTE.test(line) || HEADING.test(line)

/** Returns the URL if it is a well-formed http(s) URL, otherwise null. */
export function safeHref(raw: string): string | null {
  try {
    const url = new URL(raw)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

// code | [text](url) | **bold** | *em* | bare url
const INLINE =
  /`([^`\n]+)`|\[([^\]\n]+)\]\(\s*(https?:\/\/[^\s)]+)\s*\)|\*\*(?=\S)([\s\S]+?)(?<=\S)\*\*|(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=\S)\*(?![\w*])|(https?:\/\/[^\s<>"'`]+)/g
const TRAILING_PUNCT = /[.,;:!?'")\]}>…]+$/

export function parseInline(src: string, allowLinks = true): Inline[] {
  const out: Inline[] = []
  const pushText = (text: string) => {
    if (!text) return
    const last = out[out.length - 1]
    if (last?.type === 'text') last.text += text
    else out.push({ type: 'text', text })
  }
  const re = new RegExp(INLINE.source, 'g')
  let pos = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    const [whole, code, linkText, linkUrl, bold, em, bare] = m
    pushText(src.slice(pos, m.index))
    pos = m.index + whole.length
    if (code !== undefined) {
      out.push({ type: 'code', text: code })
    } else if (linkText !== undefined) {
      const href = allowLinks ? safeHref(linkUrl) : null
      if (href) out.push({ type: 'link', href, children: parseInline(linkText, false) })
      else out.push(...parseInline(linkText, false))
    } else if (bold !== undefined) {
      out.push({ type: 'strong', children: parseInline(bold, allowLinks) })
    } else if (em !== undefined) {
      out.push({ type: 'em', children: parseInline(em, allowLinks) })
    } else if (bare !== undefined) {
      const url = bare.replace(TRAILING_PUNCT, '')
      pos = m.index + url.length
      re.lastIndex = pos
      const href = allowLinks ? safeHref(url) : null
      if (href) out.push({ type: 'link', href, children: [{ type: 'text', text: prettyUrl(url) }] })
      else pushText(url)
    }
  }
  pushText(src.slice(pos))
  return out
}

/** "https://brand.uic.edu/messaging/voice-and-tone/" -> "brand.uic.edu/messaging/voice-and-tone" */
export function prettyUrl(url: string): string {
  return url.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '')
}

export function parseBlocks(src: string, depth = 0): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (isBlank(line)) {
      i++
      continue
    }

    if (depth < MAX_QUOTE_DEPTH && QUOTE.test(line)) {
      const inner: string[] = []
      // Quote lines, plus "lazy" continuation lines that aren't another block.
      while (i < lines.length && !isBlank(lines[i]) && (QUOTE.test(lines[i]) || !isBlockStart(lines[i]))) {
        const q = QUOTE.exec(lines[i])
        inner.push(q ? q[1] : lines[i])
        i++
      }
      blocks.push({ type: 'quote', blocks: parseBlocks(inner.join('\n'), depth + 1) })
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ type: 'heading', content: parseInline(heading[1]) })
      i++
      continue
    }

    const ordered = ORDERED.test(line)
    if (ordered || BULLET.test(line)) {
      const marker = ordered ? ORDERED : BULLET
      const items: string[] = []
      while (i < lines.length) {
        const cur = lines[i]
        const item = marker.exec(cur)
        if (item) {
          items.push(item[1])
          i++
        } else if (!isBlank(cur) && !isBlockStart(cur)) {
          items[items.length - 1] += ` ${cur.trim()}`
          i++
        } else if (isBlank(cur)) {
          // A blank line continues the list only if the next non-blank line is another item.
          let j = i
          while (j < lines.length && isBlank(lines[j])) j++
          if (j < lines.length && marker.test(lines[j])) i = j
          else break
        } else break
      }
      blocks.push({ type: 'list', ordered, items: items.map((t) => parseInline(t.trim())) })
      continue
    }

    const para: string[] = []
    while (i < lines.length && !isBlank(lines[i]) && (para.length === 0 || !isBlockStart(lines[i]))) {
      para.push(lines[i].trim())
      i++
    }
    blocks.push({ type: 'paragraph', lines: para.map((l) => parseInline(l)) })
  }
  return blocks
}

/** Markdown -> readable plain text (for screen-reader announcements and "Copy"). */
export function toPlainText(src: string): string {
  return src
    .replace(/\r\n?/g, '\n')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}[*•]\s+/gm, '- ')
    .replace(/\[([^\]\n]+)\]\(\s*(https?:\/\/[^\s)]+)\s*\)/g, '$1 ($2)')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Markdown from '../chat/Markdown'
import { parseBlocks, parseInline, safeHref, toPlainText } from '../chat/markdownParser'

describe('chat markdown parser', () => {
  it('auto-links bare URLs and leaves trailing punctuation outside', () => {
    const nodes = parseInline('See https://brand.uic.edu/messaging/voice-and-tone/, then (https://uic.edu).')
    const links = nodes.filter((n) => n.type === 'link')
    expect(links.map((l) => l.type === 'link' && l.href)).toEqual(['https://brand.uic.edu/messaging/voice-and-tone/', 'https://uic.edu/'])
    expect(nodes[nodes.length - 1]).toEqual({ type: 'text', text: ').' })
  })

  it('only links http(s) URLs', () => {
    expect(safeHref('javascript:alert(1)')).toBeNull()
    expect(safeHref('data:text/html,hi')).toBeNull()
    expect(safeHref('https://uic.edu')).toBe('https://uic.edu/')
    expect(parseInline('[x](javascript:alert(1))').some((n) => n.type === 'link')).toBe(false)
  })

  it('parses quotes with lazy continuation, lists and headings', () => {
    const blocks = parseBlocks('# Title\n\nIntro line\nsecond line\n\n> quoted\ncontinued\n\n1. one\n2. two\n\n- a\n\n- b')
    expect(blocks.map((b) => b.type)).toEqual(['heading', 'paragraph', 'quote', 'list', 'list'])
    const para = blocks[1]
    expect(para.type === 'paragraph' && para.lines).toHaveLength(2)
    const quote = blocks[2]
    expect(quote.type === 'quote' && quote.blocks[0].type).toBe('paragraph')
    const ul = blocks[4]
    expect(ul.type === 'list' && !ul.ordered && ul.items.length).toBe(2)
  })

  it('renders nested markdown inside guideline quotes', () => {
    const { container } = render(<Markdown text={'> **dates**: Always use numerals: May 10.'} />)
    expect(container.querySelector('figure blockquote strong')).toHaveTextContent('dates')
  })

  it('converts markdown to plain text for announcements', () => {
    expect(toPlainText('**Bold** and [link](https://uic.edu)\n> quote')).toBe('Bold and link (https://uic.edu)\nquote')
  })
})

import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRef, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearAppData } from '../layout/appData'
import Dialog from '../layout/Dialog'
import ErrorBoundary from '../layout/ErrorBoundary'
import { useFocusTrap } from '../layout/useFocusTrap'

function Boom({ when = true }: { when?: boolean }): React.ReactNode {
  if (when) throw new Error('Kaboom')
  return <p>Recovered</p>
}

describe('ErrorBoundary', () => {
  let consoleError: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    // React logs caught render errors; keep test output clean.
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => consoleError.mockRestore())

  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('shows a friendly page fallback with Reload when a child throws', async () => {
    const onReload = vi.fn()
    render(
      <ErrorBoundary onReload={onReload}>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
    expect(screen.getByText('Kaboom')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reload' }))
    expect(onReload).toHaveBeenCalledTimes(1)
  })

  it('"Reset app data" clears only this app’s saved keys, then reloads', async () => {
    localStorage.setItem('uic-editorial:text', '"draft"')
    localStorage.setItem('uic-editorial:analysis', '{}')
    localStorage.setItem('someone-else', 'keep me')
    const onReload = vi.fn()
    render(
      <ErrorBoundary onReload={onReload}>
        <Boom />
      </ErrorBoundary>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Reset app data' }))
    expect(localStorage.getItem('uic-editorial:text')).toBeNull()
    expect(localStorage.getItem('uic-editorial:analysis')).toBeNull()
    expect(localStorage.getItem('someone-else')).toBe('keep me')
    expect(onReload).toHaveBeenCalledTimes(1)
  })

  it('section variant isolates a broken panel and can try again', async () => {
    function Harness() {
      const [broken, setBroken] = useState(true)
      return (
        <>
          <button type="button" onClick={() => setBroken(false)}>
            Fix it
          </button>
          <ErrorBoundary variant="section" label="the comparison view">
            <Boom when={broken} />
          </ErrorBoundary>
          <p>Sibling still here</p>
        </>
      )
    }
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.getByRole('alert')).toHaveTextContent('We couldn’t show the comparison view.')
    expect(screen.getByText('Sibling still here')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Fix it' }))
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(screen.getByText('Recovered')).toBeInTheDocument()
  })
})

describe('clearAppData', () => {
  it('removes every uic-editorial: key', () => {
    localStorage.setItem('uic-editorial:a', '1')
    localStorage.setItem('uic-editorial:b', '2')
    localStorage.setItem('other', '3')
    clearAppData()
    expect(Object.keys(localStorage)).toEqual(['other'])
  })
})

describe('Dialog', () => {
  function Harness() {
    const [open, setOpen] = useState(false)
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open
        </button>
        <Dialog open={open} onClose={() => setOpen(false)} title="Hello" description="A test dialog">
          <button type="button">Inside</button>
        </Dialog>
      </>
    )
  }

  it('is labelled, traps focus, locks scroll and restores focus on Esc', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open' })
    await user.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Hello' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleDescription('A test dialog')
    expect(document.body.style.overflow).toBe('hidden')
    expect(screen.getByRole('button', { name: 'Close dialog' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Inside' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Close dialog' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
    expect(document.body.style.overflow).toBe('')
  })
})

describe('useFocusTrap', () => {
  it('retries the initial focus on the next frame if the container was not focusable yet', async () => {
    function Trap() {
      const ref = useRef<HTMLDivElement>(null)
      useFocusTrap(ref, true)
      return (
        <div ref={ref}>
          <button type="button">Inside</button>
        </div>
      )
    }
    const original = HTMLElement.prototype.focus
    let refusals = 1
    const spy = vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function (this: HTMLElement, opts?: FocusOptions) {
      if (refusals-- > 0) return // e.g. still visibility:hidden at the start of a transition
      original.call(this, opts)
    })
    render(<Trap />)
    expect(screen.getByRole('button', { name: 'Inside' })).not.toHaveFocus()
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(null)))
    })
    expect(screen.getByRole('button', { name: 'Inside' })).toHaveFocus()
    spy.mockRestore()
  })
})

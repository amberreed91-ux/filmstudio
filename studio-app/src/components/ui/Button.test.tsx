// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Button } from './Button'

afterEach(cleanup)

const button = (name?: string) =>
  name
    ? (screen.getByRole('button', { name }) as HTMLButtonElement)
    : (screen.getByRole('button') as HTMLButtonElement)

describe('Button', () => {
  it('defaults to type="button" so it never submits a surrounding form by accident', () => {
    render(<Button>Save</Button>)
    expect(button('Save').getAttribute('type')).toBe('button')
  })

  it('honours an explicit type="submit"', () => {
    render(<Button type="submit">Send</Button>)
    expect(button('Send').getAttribute('type')).toBe('submit')
  })

  it('exposes in-flight state to assistive technology via aria-busy', () => {
    render(<Button loading>Saving</Button>)
    expect(button().getAttribute('aria-busy')).toBe('true')
    expect(button().disabled).toBe(true)
  })

  it('does not set aria-busy when idle', () => {
    render(<Button>Save</Button>)
    expect(button().hasAttribute('aria-busy')).toBe(false)
  })

  it('shows the loading label while loading and the normal children when idle', () => {
    const { rerender } = render(<Button loading loadingLabel="Creating…">Create project</Button>)
    expect(button().textContent).toContain('Creating…')
    expect(button().textContent).not.toContain('Create project')

    rerender(<Button loadingLabel="Creating…">Create project</Button>)
    expect(button().textContent).toContain('Create project')
  })

  it('hides the leading icon while loading', () => {
    const { container, rerender } = render(
      <Button icon={<svg data-testid="icon" />}>Save</Button>,
    )
    expect(container.querySelector('[data-testid="icon"]')).toBeTruthy()

    rerender(<Button loading icon={<svg data-testid="icon" />}>Save</Button>)
    expect(container.querySelector('[data-testid="icon"]')).toBeNull()
  })

  it('does not fire onClick while loading', () => {
    const onClick = vi.fn()
    render(<Button loading onClick={onClick}>Save</Button>)
    fireEvent.click(button())
    expect(onClick).not.toHaveBeenCalled()
  })

  it('fires onClick when idle', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Save</Button>)
    fireEvent.click(button())
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('applies a consistent disabled treatment and blocks clicks', () => {
    const onClick = vi.fn()
    render(<Button disabled onClick={onClick}>Save</Button>)
    expect(button().disabled).toBe(true)
    expect(button().className).toContain('disabled:opacity-45')
    fireEvent.click(button())
    expect(onClick).not.toHaveBeenCalled()
  })

  it('applies variant and size classes', () => {
    render(<Button variant="primary" size="lg">Go</Button>)
    const el = button('Go')
    expect(el.className).toContain('bg-[#ffd165]')
    expect(el.className).toContain('min-h-12')
  })

  it('exposes a consistent focus ring', () => {
    render(<Button>Save</Button>)
    const el = button()
    expect(el.className).toContain('focus-visible:outline-2')
    expect(el.className).toContain('focus-visible:outline-amber-200')
  })
})

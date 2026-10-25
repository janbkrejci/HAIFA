import { vi } from 'vitest'

/** DOM-backed stand-in: App tests also exercise capture before xterm stops bubbling. */
export class MockTerminal {
  static instances: MockTerminal[] = []
  cols = 100
  rows = 30
  textarea = document.createElement('textarea')
  data: (value: string) => void = () => {}
  constructor() { MockTerminal.instances.push(this) }
  loadAddon = vi.fn()
  write = vi.fn()
  reset = vi.fn()
  dispose = vi.fn()
  focus = vi.fn(() => this.textarea.focus())
  open = vi.fn((host: HTMLElement) => {
    this.textarea.className = 'xterm-helper-textarea'
    this.textarea.addEventListener('keydown', event => event.stopPropagation())
    host.append(this.textarea)
  })
  onData = vi.fn((callback: (data: string) => void) => {
    this.data = callback
    return { dispose: vi.fn() }
  })
}
export class MockFitAddon { fit = vi.fn() }

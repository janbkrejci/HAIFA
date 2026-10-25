import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { MockTerminal } from './xtermMock'
import TerminalOverlay from './TerminalOverlay.vue'
vi.mock('@xterm/xterm', async () => ({ Terminal: (await import('./xtermMock')).MockTerminal }))
vi.mock('@xterm/addon-fit', async () => ({ FitAddon: (await import('./xtermMock')).MockFitAddon }))
const wrappers: VueWrapper[] = []
function mountOverlay() {
  const wrapper = mount(TerminalOverlay, { attachTo: document.body })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(async () => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  await flushPromises()
  vi.unstubAllGlobals()
})
let resize: () => void
const disconnect = vi.fn()
beforeEach(() => {
  MockTerminal.instances = []
  disconnect.mockClear()
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback }
    observe() {}
    disconnect = disconnect
  })
})
function api(info = { enabled: true, pty: true }) {
  let output!: ReadableStreamDefaultController<Uint8Array>
  const cancel = vi.fn()
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.endsWith('/stream')) return new Response(new ReadableStream({ start(controller) { output = controller }, cancel }))
    return new Response(JSON.stringify({ ok: true, data: url === '/api/terminal'
      ? { ...info, cwd: '/home/me', shell: 'sh' } : { id: 'test' } }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, cancel, output: () => output }
}
describe('TerminalOverlay', () => {
  it('creates a fitted PTY, focuses xterm, writes raw bytes, and forwards ordered input and resizing', async () => {
    const { fetchMock, output } = api()
    const wrapper = mountOverlay()
    await flushPromises()
    const term = MockTerminal.instances[0]!
    expect(document.activeElement).toBe(term.textarea)
    expect(fetchMock).toHaveBeenCalledWith('/api/terminal/sessions', expect.objectContaining({ body: JSON.stringify({ cols: 100, rows: 30, cwd: '/home/me' }) }))
    const bytes = new Uint8Array([27, 91, 72, 0xc4])
    output().enqueue(bytes)
    await flushPromises()
    expect(term.write).toHaveBeenCalledWith(bytes)
    for (const data of ['a', '\u0003', '\u001a', '\t', '\u001b[A', '\u001bOP']) term.data(data)
    await flushPromises()
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/input')).map(([, init]) => JSON.parse(init!.body as string).data)).toEqual(['a', '\u0003', '\u001a', '\t', '\u001b[A', '\u001bOP'])
    term.cols = 140
    term.rows = 50
    resize()
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/terminal/sessions/test/resize', expect.objectContaining({ body: JSON.stringify({ cols: 140, rows: 50 }) }))
    await wrapper.get('textarea').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toBeUndefined()
  })
  it.each(['cross', 'unmount', 'pagehide'])('deletes and cancels the session on %s', async action => {
    const { fetchMock, cancel } = api()
    const wrapper = mountOverlay()
    await flushPromises()
    const term = MockTerminal.instances[0]!
    if (action === 'cross') await wrapper.get('#terminal-close').trigger('click')
    else if (action === 'unmount') wrapper.unmount()
    else window.dispatchEvent(new Event('pagehide'))
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/terminal/sessions/test', { method: 'DELETE', keepalive: true })
    expect(cancel).toHaveBeenCalledOnce()
    expect(disconnect).toHaveBeenCalledOnce()
    expect(term.dispose).toHaveBeenCalledOnce()
    if (action === 'cross') expect(wrapper.emitted('close')).toHaveLength(1)
  })
  it('offers Enter to restart after EOF without duplicate sessions', async () => {
    const { fetchMock, output } = api()
    const wrapper = mountOverlay()
    await flushPromises()
    output().close()
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('Nové sezení (Enter)')
    const term = MockTerminal.instances[0]!
    term.data('\r')
    term.data('\r')
    await flushPromises()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/terminal/sessions')).toHaveLength(2)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })
  it.each([{ enabled: false, pty: true }, { enabled: true, pty: false }])('explains unavailable terminal: %j', async info => {
    const { fetchMock } = api(info)
    const wrapper = mountOverlay()
    await flushPromises()
    expect(wrapper.text()).toContain(info.enabled ? 'Interaktivní terminál na tomto stroji není dostupný.' : 'na tomto počítači (loopback)')
    expect(MockTerminal.instances).toHaveLength(0)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('deletes a session whose creation completes after unmount', async () => {
    const { fetchMock } = api()
    let resolve!: (response: Response) => void
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url, init) => url === '/api/terminal/sessions'
      ? new Promise<Response>(done => { resolve = done }) : original(url, init))
    const wrapper = mountOverlay()
    await flushPromises()
    wrapper.unmount()
    resolve(new Response(JSON.stringify({ ok: true, data: { id: 'late' } })))
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/terminal/sessions/late', { method: 'DELETE', keepalive: true })
  })
})

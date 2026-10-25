import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import TerminalOverlay from './TerminalOverlay.vue'
enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())
function api(enabled = true) {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => url === '/api/terminal'
    ? new Response(JSON.stringify({ ok: true, data: { enabled, cwd: '/home/me', shell: 'sh' } }))
    : new Response('{"type":"out","stream":"stdout","text":"ahoj\\n"}\n{"type":"out","stream":"stderr","text":"warning\\n"}\n{"type":"exit","code":0,"cwd":"/new"}\n'))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
describe('TerminalOverlay', () => {
  it('renders streams, carries cd cwd to the next command and preserves the history draft', async () => {
    const fetchMock = api()
    const wrapper = mount(TerminalOverlay, { attachTo: document.body })
    await flushPromises()
    const input = wrapper.get('input')
    expect(document.activeElement).toBe(input.element)
    await input.setValue('cd /new')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('.stdout').text()).toBe('ahoj')
    expect(wrapper.get('.stderr').text()).toBe('warning')
    expect(wrapper.get('label').text()).toBe('/new $')
    await input.setValue('draft')
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect((input.element as HTMLInputElement).value).toBe('cd /new')
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect((input.element as HTMLInputElement).value).toBe('draft')
    await input.setValue('pwd')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(JSON.parse(fetchMock.mock.calls[2]![1]!.body as string).cwd).toBe('/new')
  })
  it('closes with Escape or the cross', async () => {
    api()
    const wrapper = mount(TerminalOverlay)
    await flushPromises()
    await wrapper.get('input').trigger('keydown', { key: 'Escape' })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })
  it('explains disabled loopback access without an input', async () => {
    api(false)
    const wrapper = mount(TerminalOverlay)
    await flushPromises()
    expect(wrapper.get('[data-test="terminal-disabled"]').text()).toContain('na tomto počítači (loopback)')
    expect(wrapper.find('input').exists()).toBe(false)
  })
  it.each(['ctrl-c', 'unmount'])('aborts a running command on %s', async action => {
    api()
    const wrapper = mount(TerminalOverlay)
    await flushPromises()
    let signal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn((_url, init) => new Promise((_resolve, reject) => {
      signal = init.signal
      signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    await wrapper.get('input').setValue('sleep 10')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('input').attributes('readonly')).toBeDefined()
    if (action === 'unmount') wrapper.unmount()
    else await wrapper.get('input').trigger('keydown', { key: 'c', ctrlKey: true })
    expect(signal!.aborted).toBe(true)
    await flushPromises()
    if (action === 'ctrl-c') expect(wrapper.get('.stderr').text()).toBe('^C')
  })
})

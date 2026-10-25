import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTerminalSession, deleteTerminalSession, fetchTerminal, inputTerminal, resizeTerminal, streamTerminal } from './terminal'
afterEach(() => vi.unstubAllGlobals())
function envelope(data: unknown) { return new Response(JSON.stringify({ ok: true, data })) }
describe('terminal client', () => {
  it('loads PTY availability', async () => {
    const info = { enabled: false, cwd: '/home', shell: 'sh', pty: false }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(envelope(info)))
    expect(await fetchTerminal()).toEqual(info)
  })
  it('creates with dimensions and cwd, sends input and resize, and deletes with keepalive', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => envelope({ id: 'a/b' }))
    vi.stubGlobal('fetch', fetchMock)
    const size = { cols: 120, rows: 40 }
    expect(await createTerminalSession(size, '/home')).toEqual({ id: 'a/b' })
    await inputTerminal('a/b', '\u0003\u001b[Ač')
    await resizeTerminal('a/b', size)
    await deleteTerminalSession('a/b')
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/terminal/sessions', expect.objectContaining({ method: 'POST', body: JSON.stringify({ ...size, cwd: '/home' }) }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/terminal/sessions/a%2Fb/input', expect.objectContaining({ method: 'POST', body: JSON.stringify({ data: '\u0003\u001b[Ač' }) }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/terminal/sessions/a%2Fb/resize', expect.objectContaining({ method: 'POST', body: JSON.stringify(size) }))
    expect(fetchMock).toHaveBeenNthCalledWith(4, '/api/terminal/sessions/a%2Fb', { method: 'DELETE', keepalive: true })
  })
  it('passes split UTF-8 and VT bytes through without decoding', async () => {
    const chunks = [new Uint8Array([0xc4]), new Uint8Array([0x8d, 27, 91, 50, 74])]
    const fetchMock = vi.fn().mockResolvedValue(new Response(new ReadableStream({ start(controller) {
      chunks.forEach(chunk => controller.enqueue(chunk))
      controller.close()
    } })))
    vi.stubGlobal('fetch', fetchMock)
    const received = vi.fn()
    const controller = new AbortController()
    await streamTerminal('test', controller.signal, received)
    expect(received.mock.calls.map(([bytes]) => bytes)).toEqual(chunks)
    expect(received.mock.calls[0]![0]).toBe(chunks[0])
    expect(fetchMock).toHaveBeenCalledWith('/api/terminal/sessions/test/stream', { signal: controller.signal })
  })
  it('cancels a pending reader when aborted', async () => {
    const cancel = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }))))
    const controller = new AbortController()
    const pending = streamTerminal('test', controller.signal, vi.fn())
    await new Promise(resolve => setTimeout(resolve, 0))
    controller.abort()
    await pending
    expect(cancel).toHaveBeenCalledOnce()
  })
  it('reports server errors and missing streams', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: false, error: { code: 'disabled', message: 'Disabled' } }), { status: 403 })))
    await expect(createTerminalSession({ cols: 80, rows: 24 }, '/')).rejects.toThrow('Disabled')
    await expect(streamTerminal('test', new AbortController().signal, vi.fn())).rejects.toThrow('Disabled')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null)))
    await expect(streamTerminal('test', new AbortController().signal, vi.fn())).rejects.toThrow('stream')
  })
})

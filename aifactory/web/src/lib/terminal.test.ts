import { afterEach, describe, expect, it, vi } from 'vitest'
import { execTerminal, fetchTerminal } from './terminal'
afterEach(() => vi.unstubAllGlobals())
describe('terminal client', () => {
  it('loads status', async () => {
    const info = { enabled: false, cwd: '/home', shell: 'sh' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, data: info }))))
    expect(await fetchTerminal()).toEqual(info)
  })
  it('decodes split UTF-8, output and exit without a final newline', async () => {
    const events = [{ type: 'out', stream: 'stdout', text: 'ahoj čau\n' }, { type: 'out', stream: 'stderr', text: 'oops\n' }, { type: 'exit', code: 0, cwd: '/new' }]
    const bytes = new TextEncoder().encode(events.map(event => JSON.stringify(event)).join('\n'))
    const fetchMock = vi.fn().mockResolvedValue(new Response(new ReadableStream({ start(controller) {
      for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
      controller.close()
    } })))
    vi.stubGlobal('fetch', fetchMock)
    const received = vi.fn()
    const controller = new AbortController()
    await execTerminal('cd /new', '/old', controller.signal, received)
    expect(received.mock.calls.map(([event]) => event)).toEqual(events)
    expect(fetchMock).toHaveBeenCalledWith('/api/terminal/exec', expect.objectContaining({ signal: controller.signal, body: JSON.stringify({ command: 'cd /new', cwd: '/old' }) }))
  })
  it('propagates abort', async () => {
    vi.stubGlobal('fetch', vi.fn((_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const controller = new AbortController()
    const pending = execTerminal('sleep 10', '/', controller.signal, vi.fn())
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })
  it('reports server errors and malformed or truncated streams', async () => {
    for (const response of [new Response(JSON.stringify({ ok: false, error: { code: 'disabled', message: 'Disabled' } }), { status: 403 }), new Response('{broken}\n'), new Response('{"type":"out","text":"partial"}\n')]) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
      await expect(execTerminal('echo hi', '/', new AbortController().signal, vi.fn())).rejects.toThrow()
    }
  })
})

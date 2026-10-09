import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useCodeState, type CodeStateOptions } from './code'

function envelope(data: unknown, ok = true, status = 200): Response {
  const body = ok
    ? { ok: true, data, error: null, warnings: [] }
    : { ok: false, data: null, error: { code: 'x', message: 'boom', path: null, id: null, issues: [] }, warnings: [] }
  return new Response(JSON.stringify(body), { status })
}

function host(options: CodeStateOptions = {}) {
  let state!: ReturnType<typeof useCodeState>
  const Host = defineComponent({
    setup() {
      state = useCodeState(options)
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return { wrapper, state: () => state }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useCodeState', () => {
  it('reports a stale dashboard from /api/code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => envelope({ stale: true, started: 'a', current: 'b' })))
    const { state } = host()
    await flushPromises()
    expect(state().stale.value).toBe(true)
  })

  it('restarts and reloads once the new server runs the current code', async () => {
    const answers = [
      envelope({ stale: true, started: 'old', current: 'new' }),
      envelope({ restarting: true }),
      envelope({ stale: true, started: 'old', current: 'new' }),
      envelope({ stale: false, started: 'new', current: 'new' }),
    ]
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        answers.shift() ?? envelope({ stale: false, started: 'new', current: 'new' }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const reload = vi.fn()
    const { state } = host({ reload, wait: async () => {} })
    await flushPromises()
    await state().restart()
    expect(reload).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls.some(([url, init]) => url === '/api/restart' && init?.method === 'POST')).toBe(true)
  })

  it('reports a restart that does not come back', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) =>
      url === '/api/restart' ? envelope({ restarting: true }) : envelope({ stale: true, started: 'old', current: 'new' }),
    ))
    const reload = vi.fn()
    const { state } = host({ reload, wait: async () => {} })
    await flushPromises()
    await state().restart()
    expect(reload).not.toHaveBeenCalled()
    expect(state().restarting.value).toBe(false)
    expect(state().error.value).toContain('just dash')
  })
})

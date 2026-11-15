import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useUpdates } from './updates'
import { setLocale } from './i18n'

const envelope = (data: unknown) => new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.unstubAllGlobals(); setLocale('en') })
function host(reload = vi.fn()) {
  let updates!: ReturnType<typeof useUpdates>
  wrappers.push(mount(defineComponent({ setup() {
    updates = useUpdates({ reload, wait: async () => {} })
    return () => h('div')
  } })))
  return { updates, reload }
}
describe.each(['en', 'cs'] as const)('updates (%s)', language => {
  beforeEach(() => setLocale(language))
  it('retries current and failed checks freshly', async () => {
    const fetch = vi.fn(async () => envelope({ status: 'current', current_version: '0.1.0' }))
    vi.stubGlobal('fetch', fetch)
    const { updates } = host()
    await flushPromises()
    updates.activate()
    await flushPromises()
    expect(fetch.mock.calls).toHaveLength(2)
    expect(fetch).toHaveBeenLastCalledWith('/api/updates?fresh=1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    updates.state.value.status = 'error'
    updates.activate()
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith('/api/updates?fresh=1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })
  it('installs the available update and reloads for a fresh system check after restart', async () => {
    let checks = 0
    const fetch = vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: ++checks === 1 ? 'old' : 'new', stale: false, current: 'new' })
      if (url === '/api/updates/install') return envelope({ status: 'installing' })
      return envelope({ status: 'available', current_version: '0.1.0', target_version: '0.2.0' })
    })
    vi.stubGlobal('fetch', fetch)
    const { updates, reload } = host()
    await flushPromises()
    await updates.install()
    expect(fetch).toHaveBeenCalledWith('/api/updates/install', { method: 'POST' })
    expect(reload).toHaveBeenCalledTimes(1)
  })
  it('keeps failed installation visible and does not reload', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: 'old', stale: false, current: 'old' })
      if (url === '/api/updates/install') return envelope({ status: 'installing' })
      return envelope({ status: 'error', current_version: '0.1.0', error: 'checksum mismatch' })
    }))
    const { updates, reload } = host()
    await flushPromises()
    await updates.install()
    expect(updates.state.value.error).toBe('checksum mismatch')
    expect(updates.state.value.error_code).toBe('install_failed')
    expect(reload).not.toHaveBeenCalled()
  })
  it('waits for active task runs instead of reporting a failed check', async () => {
    const fetch = vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: 'old', stale: false, current: 'old' })
      if (url === '/api/updates/install') {
        return new Response(JSON.stringify({ ok: false, data: null, error: { code: 'runs_active', message: 'Aktualizace počká, běží 1 task.' }, warnings: [] }), { status: 409 })
      }
      return envelope({ status: 'available', current_version: '0.1.0', target_version: '0.2.0' })
    })
    vi.stubGlobal('fetch', fetch)
    const { updates, reload } = host()
    await flushPromises()
    await updates.install()
    expect(updates.state.value.status).toBe('waiting')
    expect(updates.state.value.error_code).toBe('runs_active')
    expect(updates.state.value.error).toBe('Aktualizace počká, běží 1 task.')
    expect(reload).not.toHaveBeenCalled()
    updates.activate()
    await flushPromises()
    expect(fetch.mock.calls.filter(([url]) => url === '/api/updates/install')).toHaveLength(2)
  })
  it('assigns a stable code to an invalid response and clears it on retry', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(envelope({ status: 'unknown' }))
      .mockImplementation(async () => envelope({ status: 'current', current_version: '0.1.0' }))
    vi.stubGlobal('fetch', fetch)
    const { updates } = host()
    await flushPromises()
    expect(updates.state.value).toMatchObject({ status: 'error', error_code: 'invalid_response' })
    await updates.check()
    expect(updates.state.value).toMatchObject({ status: 'current', error_code: undefined })
  })
  it('keeps server check diagnostics separate from the stable code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => envelope({ status: 'error', current_version: '0.1.0', error: 'Kontrola selhala: offline' })))
    const { updates } = host()
    await flushPromises()
    expect(updates.state.value).toMatchObject({ error_code: 'check_failed', error: 'Kontrola selhala: offline' })
  })
  it('assigns an installation failure code to a rejected install request', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: 'old', stale: false })
      if (url === '/api/updates/install') return new Response(JSON.stringify({ ok: false, error: { code: 'update_unavailable', message: 'Nová aktualizace není k dispozici.' } }), { status: 409 })
      return envelope({ status: 'available', current_version: '0.1.0' })
    }))
    const { updates, reload } = host()
    await flushPromises()
    await updates.install()
    expect(updates.state.value).toMatchObject({ status: 'error', error_code: 'install_failed', error: 'Nová aktualizace není k dispozici.' })
    expect(reload).not.toHaveBeenCalled()
  })
  it('reports the restart timeout without reloading or losing its code', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: 'old', stale: false })
      return envelope({ status: 'available', current_version: '0.1.0' })
    }))
    const { updates, reload } = host()
    await flushPromises()
    await updates.install()
    expect(updates.state.value).toMatchObject({ status: 'error', error_code: 'restart_timeout' })
    expect(reload).not.toHaveBeenCalled()
  })
  it('resumes watching an installation when the page is opened during the update', async () => {
    let reads = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: 'same', stale: false, current: 'same' })
      return envelope(++reads === 1
        ? { status: 'installing', current_version: '0.1.0' }
        : { status: 'current', current_version: '0.1.1' })
    }))
    const { reload } = host()
    await flushPromises()
    expect(reload).toHaveBeenCalledTimes(1)
  })
})

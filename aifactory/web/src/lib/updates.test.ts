import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useUpdates } from './updates'

const envelope = (data: unknown) => new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.unstubAllGlobals() })
function host(reload = vi.fn()) {
  let updates!: ReturnType<typeof useUpdates>
  wrappers.push(mount(defineComponent({ setup() {
    updates = useUpdates({ reload, wait: async () => {} })
    return () => h('div')
  } })))
  return { updates, reload }
}
describe('updates', () => {
  it('retries current and failed checks freshly', async () => {
    const fetch = vi.fn(async () => envelope({ status: 'current', current_version: '0.1.0' }))
    vi.stubGlobal('fetch', fetch)
    const { updates } = host()
    await flushPromises()
    updates.activate()
    await flushPromises()
    expect(fetch.mock.calls).toHaveLength(2)
    expect(fetch).toHaveBeenLastCalledWith('/api/updates?fresh=1')
    updates.state.value.status = 'error'
    updates.activate()
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith('/api/updates?fresh=1')
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

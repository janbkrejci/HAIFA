import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/lib/i18n'
import MigrationBanner from './MigrationBanner.vue'

const { reload } = vi.hoisted(() => ({ reload: vi.fn() }))
vi.mock('@/lib/updates', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/updates')>()
  return { ...actual, useUpdates: (options: Parameters<typeof actual.useUpdates>[0]) => actual.useUpdates({ ...options, reload, wait: async () => {} }) }
})
const envelope = (data: unknown) => new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); setLocale('en') })

const labels = {
  en: { title: 'HAIFA is becoming GIRO', action: 'Click here to transition', busy: 'An update is already running.', waiting: 'The update is waiting for active tasks' },
  cs: { title: 'HAIFA se přejmenovává na GIRO', action: 'Klikněte zde pro přechod', busy: 'Aktualizace již probíhá.', waiting: 'Aktualizace čeká na dokončení běžících tasků' },
}

describe.each(['en', 'cs'] as const)('MigrationBanner (%s)', language => {
  it.each(['runs_active', 'update_busy', 'update_unavailable'] as const)('keeps %s actionable, localized and retryable', async code => {
    setLocale(language)
    let attempts = 0
    let codeReads = 0
    const fetch = vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: ++codeReads > 2 ? 'new' : 'old', stale: false })
      if (url === '/api/updates/migrate') {
        if (++attempts === 1) return new Response(JSON.stringify({ ok: false, error: { code, message: `technical: ${code}` } }), { status: 409 })
        return envelope({ status: 'installing' })
      }
      return envelope({ status: 'current', current_version: '0.1.999' })
    })
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(MigrationBanner)
    await flushPromises()
    expect(wrapper.text()).toContain(labels[language].title)
    expect(attempts).toBe(0)
    const action = wrapper.get('[data-test="migration-action"]')
    expect(action.text()).toBe(labels[language].action)
    await action.trigger('click')
    await flushPromises()
    expect(wrapper.get('pre').text()).toBe(`technical: ${code}`)
    if (code !== 'update_unavailable') expect(wrapper.get('[role="status"]').text()).toContain(code === 'runs_active' ? labels[language].waiting : labels[language].busy)
    setLocale(language === 'en' ? 'cs' : 'en')
    await flushPromises()
    expect(wrapper.text()).toContain(labels[language === 'en' ? 'cs' : 'en'].title)
    expect(wrapper.get('pre').text()).toBe(`technical: ${code}`)
    await action.trigger('click')
    await flushPromises()
    expect(attempts).toBe(2)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls.some(([url]) => url === '/api/updates/install')).toBe(false)
  })

  it('blocks duplicate clicks while the request is pending and hides on GIRO', async () => {
    let finish!: (value: Response) => void
    let posts = 0
    let reads = 0
    let giro = false
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: ++reads > 1 ? 'new' : 'old', stale: false })
      if (url === '/api/updates/migrate') { posts++; return new Promise<Response>(resolve => { finish = resolve }) }
      return envelope({ status: 'current', current_version: giro ? '1.0.1' : '0.1.999' })
    }))
    const wrapper = mount(MigrationBanner)
    await flushPromises()
    const action = wrapper.get('[data-test="migration-action"]')
    await action.trigger('click')
    await flushPromises()
    expect(action.attributes('disabled')).toBeDefined()
    await action.trigger('click')
    expect(posts).toBe(1)
    finish(envelope({ status: 'installing' }))
    await flushPromises()
    expect(reload).toHaveBeenCalledOnce()
    giro = true
    const restarted = mount(MigrationBanner)
    await flushPromises()
    expect(restarted.find('[data-test="migration-banner"]').exists()).toBe(false)
  })
})

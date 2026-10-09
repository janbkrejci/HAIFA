import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import SettingsView from './SettingsView.vue'
import { DIRTY_STATUS, SETTINGS } from '@/test/settingsFixtures'
import { resetConfigStatusForTests, useConfigStatus } from '@/lib/configStatus'

function ok(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

function fail(code: string, issues: unknown[] = [], status = 422) {
  const error = { code, message: 'invalid settings', path: null, id: null, issues }
  return new Response(JSON.stringify({ ok: false, data: null, error, warnings: [] }), { status })
}

type Handler = (url: string, init?: RequestInit) => Response

function stub(post: Handler) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return post(url, init)
    if (url === '/api/repos/haifa/config/status') return ok(DIRTY_STATUS)
    return ok(SETTINGS)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetConfigStatusForTests()
})

describe('SettingsView', () => {
  it('loads and shows the settings', async () => {
    stub(() => ok(SETTINGS))
    const wrapper = mount(SettingsView)
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Nastavení')
    expect((wrapper.get('[data-test="backlog_dir"]').element as HTMLInputElement).value).toBe(
      'backlog',
    )
  })

  it('shows an API error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => fail('invalid_config', [], 500)))
    const wrapper = mount(SettingsView)
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toContain('invalid settings')
  })

  it('saves the changed values and refreshes the config status', async () => {
    const saved = { ...SETTINGS, shared: { ...SETTINGS.shared, base: 'develop' }, saved: ['shared'] }
    const fetch = stub(() => ok(saved))
    const wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.get('[data-test="base"]').setValue('develop')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/settings')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ shared: { base: 'develop' } })
    expect(wrapper.find('[data-test="saved"]').exists()).toBe(true)
    expect(fetch.mock.calls.some(([url]) => url === '/api/repos/haifa/config/status')).toBe(true)
    expect(useConfigStatus().status.value?.clean).toBe(false)
    expect((wrapper.get('[data-test="base"]').element as HTMLInputElement).value).toBe('develop')
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeDefined()
  })

  it('shows a rejected value at its field and keeps the input', async () => {
    stub(() =>
      fail('invalid_value', [
        {
          code: 'invalid_value',
          message: 'must not be empty',
          path: '.factory/config.yaml',
          id: 'base',
        },
      ]),
    )
    const wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.get('[data-test="base"]').setValue('  ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-test="error-base"]').text()).toBe('must not be empty')
    expect(wrapper.get('[data-test="base"]').attributes('aria-invalid')).toBe('true')
    expect((wrapper.get('[data-test="base"]').element as HTMLInputElement).value).toBe('  ')
    expect(wrapper.find('[data-test="saved"]').exists()).toBe(false)
  })
})

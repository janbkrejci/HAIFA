import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import SettingsView from './SettingsView.vue'
import { DIRTY_STATUS, SETTINGS } from '@/test/settingsFixtures'
import { deferred } from '@/test/deferred'
import { resetConfigStatusForTests } from '@/lib/configStatus'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetConfigStatusForTests()
})

describe('SettingsView spinner', () => {
  it('spins Uložit until the save answers', async () => {
    const save = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST') return save.promise
        if (url === '/api/repos/haifa/config/status') return ok(DIRTY_STATUS)
        return ok(SETTINGS)
      }),
    )
    const wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.get('[data-test="base"]').setValue('develop')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="save"] [data-test="spinner"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="reset"]').attributes('disabled')).toBeDefined()
    save.resolve(ok({ ...SETTINGS, shared: { ...SETTINGS.shared, base: 'develop' }, saved: ['shared'] }))
    await flushPromises()
    expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(0)
    expect(wrapper.get('[data-test="reset"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})

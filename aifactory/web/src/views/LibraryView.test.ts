import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import LibraryView from './LibraryView.vue'
import { answerDialog, openDialog } from '@/test/modal'
const items = ['agent', 'workflow', 'skill', 'extension'].map(type => ({ type, name: type + '-demo', n: 2, version: 'sha256:123456789', short_version: '12345678', purpose: type === 'agent' ? 'Build code' : null, description: 'Description ' + type, date: '2026-10-08', author: 'Team' }))
function envelope(data: unknown) { return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] })) }
function api(handler?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const own = handler?.(url, init); if (own) return own
    if (url === '/api/library') return envelope({ exists: true, items })
    if (url.startsWith('/api/library/items/')) {
      const item = items.find(i => url.includes('/' + i.type + '/'))!
      return envelope({ ...item, ...(url.includes('version=old-hash') ? { version: 'old-hash' } : {}), files: [{ path: 'system.md', content: 'Read-only prompt', binary: false }], history: [{ n: 1, version: 'old-hash', short_version: 'old-hash', date: 'yesterday', author: 'Other' }, { n: 2, version: item.version, short_version: item.short_version, date: item.date, author: item.author }] })
    }
    if (url === '/api/library/plan') return envelope({ digest: 'import-digest', files: [{ path: 'SKILL.md', content: 'IMPORT FILE CONTENT' }], items: [], blockers: [] })
    if (url === '/api/library/apply') return envelope({ commit: 'import-commit' })
    throw new Error(url)
  })
  vi.stubGlobal('fetch', mock); return mock
}
async function openAgent() {
  const wrapper = mount(LibraryView, { attachTo: document.body }); await flushPromises()
  await wrapper.get('[data-test="library-item"] button').trigger('click'); await flushPromises(); return wrapper
}
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })
describe('Library', () => {
  it('shows tabs and row metadata without repo usage', async () => {
    api(); const wrapper = mount(LibraryView); await flushPromises()
    expect(wrapper.get('[data-test="library-item"]').text()).toContain('v2 · 12345678')
    expect(wrapper.get('[data-test="library-item"]').text()).toContain('Build code')
    expect(wrapper.text()).not.toContain('Použití')
    for (const type of ['workflow', 'skill', 'extension']) {
      await wrapper.get(`[data-test="tab-${type}"]`).trigger('click')
      expect(wrapper.get('[data-test="library-item"]').text()).toContain('Description ' + type)
    }
  })
  it('shows read-only files and history; loads a historical version', async () => {
    const mock = api(); const wrapper = await openAgent()
    expect(wrapper.get('[data-test="item-file"] pre').text()).toBe('Read-only prompt')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.find('[data-test="item-usage"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="item-add"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="item-old-version"]').exists()).toBe(false)
    await wrapper.get('[data-test="item-history"] button').trigger('click'); await flushPromises()
    expect(mock).toHaveBeenCalledWith('/api/library/items/agent/agent-demo?version=old-hash')
    expect(wrapper.get('[data-test="item-old-version"]').text()).toContain('Prohlížíš starší verzi')
  })
  it('imports a folder only after preview and confirmation, without uploading content', async () => {
    const mock = api(); const wrapper = await openAgent()
    await wrapper.get('[data-test="library-import"]').trigger('click'); await flushPromises()
    const field = openDialog()!.querySelector<HTMLInputElement>('[data-test=import-path]')!
    field.value = '~/skills/demo'; field.dispatchEvent(new Event('input', { bubbles: true }))
    const type = openDialog()!.querySelector<HTMLButtonElement>('[data-test="import-type"]')!
    type.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await flushPromises()
    expect(mock.mock.calls.some(([url]) => url === '/api/library/plan')).toBe(false)
    type.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }))
    type.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await flushPromises()
    expect(type.dataset.value).toBe('extension')
    expect(mock.mock.calls.some(([url]) => url === '/api/library/plan')).toBe(false)
    await answerDialog(true)
    expect(openDialog()?.textContent).toContain('IMPORT FILE CONTENT')
    expect(mock.mock.calls.some(([url]) => url === '/api/library/apply')).toBe(false)
    await answerDialog(true)
    const body = JSON.parse(mock.mock.calls.find(([url]) => url === '/api/library/apply')![1]!.body as string)
    expect(body).toEqual({ action: 'import', options: { path: '~/skills/demo', type: 'extension' }, digest: 'import-digest' })
    expect(wrapper.text()).toContain('Import dokončen')
    expect(wrapper.find('[data-test="library-detail"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="library-item"]').text()).toContain('extension-demo')
  })
})

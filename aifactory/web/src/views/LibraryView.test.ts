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
    if (url === '/api/library/overrides') return envelope({ library: 'abc', overrides: [], errors: [] })
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
  it('lists the repos that override an item, shows the diff and moves the copy after confirmation', async () => {
    const plan = { action: 'move', type: 'agent', name: 'agent-demo', base: 'main', base_sha: 'b', digest: 'move-digest', target: 'base', library: 'abcdef1234',
      files: [{ path: '.factory/prompts/agent-demo/system.md', action: 'delete', diff: '', content: null, binary: false }], blockers: [],
      library_plan: { digest: 'l', files: [{ path: 'agents/agent-demo/system.md', action: 'modify', diff: '-old\n+REPO COPY', content: null, binary: false }] } }
    const mock = api((url) => {
      if (url === '/api/library/overrides') return envelope({ library: 'abc', overrides: [{ repo: 'web', repo_name: 'Web', type: 'agent', name: 'agent-demo', same: false }], errors: [] })
      if (url === '/api/repos/web/factory/plan') return envelope(plan)
      if (url === '/api/repos/web/factory/apply') return envelope({ ...plan, library_commit: 'feedbeef00' })
    })
    const wrapper = await openAgent()
    expect(wrapper.get('[data-test="override-count-agent-demo"]').text()).toBe('1')
    expect(wrapper.get('[data-test="item-overrides"]').text()).toContain('Web')
    await wrapper.get('[data-test="override-diff"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test="override-plan"]').text()).toContain('agents/agent-demo/system.md')
    expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/repos/web/factory/plan')![1]!.body))).toEqual({ action: 'move', options: { type: 'agent', name: 'agent-demo' }, target: 'base' })
    expect(mock.mock.calls.some(([url]) => url === '/api/repos/web/factory/apply')).toBe(false)
    await wrapper.get('[data-test="override-move-apply"]').trigger('click'); await flushPromises()
    await answerDialog(true)
    const body = JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/repos/web/factory/apply')![1]!.body))
    expect(body).toEqual({ action: 'move', options: { type: 'agent', name: 'agent-demo' }, target: 'base', digest: 'move-digest' })
    expect(wrapper.text()).toContain('je v knihovně')
  })
  it('re-seeds after a preview; an item the team changed is overwritten only when ticked', async () => {
    const kept = { type: 'agent', name: 'builder', action: 'kept', version: 'sha256:new', diff: [{ path: 'agents/builder/system.md', action: 'modify', diff: '-team\n+seed', content: null, binary: false }] }
    const mock = api((url, init) => {
      if (url === '/api/library/plan') {
        const body = JSON.parse(String(init!.body))
        const taken = body.options.take?.includes('agent/builder')
        return envelope({ digest: taken ? 'take-digest' : 'seed-digest', blockers: [],
          files: taken ? [{ path: 'agents/builder/system.md', action: 'modify', diff: '', content: null, binary: false }] : [{ path: 'workflows/quality.yaml', action: 'create', diff: '', content: 'x', binary: false }],
          items: [taken ? { ...kept, action: 'take', diff: undefined } : kept, { type: 'workflow', name: 'quality', action: 'create' }] })
      }
      if (url === '/api/library/apply') return envelope({ commit: 'seedcommit1' })
    })
    const wrapper = mount(LibraryView, { attachTo: document.body }); await flushPromises()
    await wrapper.get('[data-test="library-reseed"]').trigger('click'); await flushPromises()
    expect(openDialog()?.textContent).toContain('workflow/quality')
    expect(openDialog()?.textContent).toContain('agents/builder/system.md')
    const box = openDialog()!.querySelector<HTMLInputElement>('[data-test="seed-take-agent/builder"]')!
    expect(box.checked).toBe(false)
    box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
    expect(openDialog()?.textContent).toContain('agents/builder/system.md')
    await answerDialog(true)
    const body = JSON.parse(mock.mock.calls.find(([url]) => url === '/api/library/apply')![1]!.body as string)
    expect(body).toEqual({ action: 'seed', options: { take: ['agent/builder'] }, digest: 'take-digest' })
    expect(wrapper.text()).toContain('Výchozí agenti a workflows obnoveny')
  })
  it('shows the sync state and pulls, pushes or connects a remote', async () => {
    let remote: string | null = null
    const mock = api((url) => {
      if (url === '/api/library' || url === '/api/library?fetch=1') return envelope({ exists: true, items, library: '/h/library', remote, branch: 'main', ahead: remote ? 0 : null, behind: remote ? 2 : null, dirty: false })
      if (url === '/api/library/remote') { remote = 'https://example.test/lib.git'; return envelope({ pushed: true }) }
      if (url === '/api/library/pull') return envelope({ pulled: 2 })
    })
    const wrapper = mount(LibraryView); await flushPromises()
    expect(wrapper.get('[data-test="library-sync-state"]').text()).toContain('Bez remote')
    await wrapper.get('[data-test="library-remote-url"]').setValue('https://example.test/lib.git')
    await wrapper.get('[data-test="library-connect"]').trigger('submit'); await flushPromises()
    expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/library/remote')![1]!.body))).toEqual({ url: 'https://example.test/lib.git' })
    expect(wrapper.get('[data-test="library-sync-state"]').text()).toContain('Pozadu o 2')
    await wrapper.get('[data-test="library-fetch"]').trigger('click'); await flushPromises()
    expect(mock.mock.calls.some(([url]) => url === '/api/library?fetch=1')).toBe(true)
    await wrapper.get('[data-test="library-pull"]').trigger('click'); await flushPromises()
    expect(mock.mock.calls.some(([url]) => url === '/api/library/pull')).toBe(true)
    expect(wrapper.text()).toContain('Stažení z remote dokončeno')
  })
  it('tells local changes, a pending pull request and a library in sync apart', async () => {
    const pr = { branch: 'haifa-library/20261013-abc', base: 'main', title: 'library: import skill/lint', created: 'now', repo: 'janbkrejci/HAIFA-LIBRARY', head_repo: 'ada/HAIFA-LIBRARY', url: 'https://github.com/janbkrejci/HAIFA-LIBRARY/pull/7', number: 7, state: 'OPEN', fork: true }
    let status: Record<string, unknown> = { ahead: 1, unsent: 1, pull_requests: [] }
    const mock = api((url) => {
      if (url === '/api/library' || url === '/api/library?fetch=1') return envelope({ exists: true, items, library: '/h/library', remote: 'https://github.com/janbkrejci/HAIFA-LIBRARY.git', branch: 'main', behind: 0, dirty: false, ...status })
      if (url === '/api/library/push') { status = { ahead: 1, unsent: 0, pull_requests: [pr] }; return envelope({ pushed: 1, pull_request: pr }) }
    })
    const wrapper = mount(LibraryView); await flushPromises()
    expect(wrapper.get('[data-test="library-sync-state"]').text()).toContain('Lokální změny')
    expect(wrapper.find('[data-test="library-no-prs"]').exists()).toBe(true)
    await wrapper.get('[data-test="library-push"]').trigger('click'); await flushPromises()
    expect(mock.mock.calls.some(([url]) => url === '/api/library/push')).toBe(true)
    expect(wrapper.text()).toContain('PR #7 z forku ada/HAIFA-LIBRARY')
    expect(wrapper.get('[data-test="library-sync-state"]').text()).toContain('Čeká v PR')
    expect(wrapper.get('[data-test="library-pr"] a').attributes('href')).toBe(pr.url)
    expect(wrapper.get('[data-test="library-push"]').attributes('disabled')).toBeDefined()
    status = { ahead: 0, unsent: 0, pull_requests: [] }
    await wrapper.get('[data-test="library-fetch"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test="library-sync-state"]').text()).toContain('Srovnáno s remote')
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import LibrarySection from './LibrarySection.vue'
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
  const wrapper = mount(LibrarySection, { props: { findings: [] }, attachTo: document.body }); await flushPromises()
  await wrapper.get('[data-test="library-item"] button').trigger('click'); await flushPromises(); return wrapper
}
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })
describe('LibrarySection', () => {
  it('shows tabs and row metadata without repo usage', async () => {
    api(); const wrapper = mount(LibrarySection, { props: { findings: [] } }); await flushPromises()
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
    const wrapper = mount(LibrarySection, { props: { findings: [] }, attachTo: document.body }); await flushPromises()
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
  it('styles the seed confirm like every confirm dialog, danger only when it overwrites a ticked item', async () => {
    const kept = { type: 'agent', name: 'builder', action: 'kept', version: 'sha256:new', diff: [] }
    api((url, init) => {
      if (url === '/api/library/plan') {
        const taken = JSON.parse(String(init!.body)).options.take?.includes('agent/builder')
        return envelope({ digest: 'd', blockers: [], files: [{ path: 'workflows/quality.yaml', action: 'create', diff: '', content: 'x', binary: false }],
          items: [taken ? { ...kept, action: 'take' } : kept] })
      }
    })
    const wrapper = mount(LibrarySection, { props: { findings: [] }, attachTo: document.body }); await flushPromises()
    await wrapper.get('[data-test="library-reseed"]').trigger('click'); await flushPromises()
    const ok = () => openDialog()!.querySelector<HTMLButtonElement>('[data-test="confirm-ok"]')!
    expect(ok().classList.contains('ok')).toBe(true)
    expect(ok().classList.contains('danger')).toBe(false)
    expect(ok().disabled).toBe(false)
    const box = openDialog()!.querySelector<HTMLInputElement>('[data-test="seed-take-agent/builder"]')!
    box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
    expect(ok().classList.contains('danger')).toBe(true)
    expect(ok().textContent).toContain('Přepsat a obnovit')
  })
  it('shows a seed dialog with nothing to do without a faded confirm button', async () => {
    api((url) => { if (url === '/api/library/plan') return envelope({ digest: 'd', blockers: [], files: [], items: [{ type: 'agent', name: 'builder', action: 'unchanged' }] }) })
    const wrapper = mount(LibrarySection, { props: { findings: [] }, attachTo: document.body }); await flushPromises()
    await wrapper.get('[data-test="library-reseed"]').trigger('click'); await flushPromises()
    expect(openDialog()!.querySelector('[data-test="seed-nothing"]')).not.toBeNull()
    expect(openDialog()!.querySelector('[data-test="confirm-ok"]')).toBeNull()
    expect(openDialog()!.querySelector('[data-test="confirm-cancel"]')!.textContent).toContain('Zavřít')
    await answerDialog(false)
    expect(openDialog()).toBeNull()
  })
  it('picks the import folder with the path field or the folder browser of the Add repository page', async () => {
    api((url) => {
      if (url === '/api/fs/dirs') return envelope({ path: '/home/ada', parent: '/home', entries: [{ name: 'skills', path: '/home/ada/skills', is_git: false, has_factory: false }], truncated: false })
      if (url.startsWith('/api/fs/dirs?path=')) return envelope({ path: '/home/ada/skills', parent: '/home/ada', entries: [], truncated: false })
    })
    const wrapper = mount(LibrarySection, { props: { findings: [] }, attachTo: document.body }); await flushPromises()
    await wrapper.get('[data-test="library-import"]').trigger('click'); await flushPromises()
    const field = openDialog()!.querySelector<HTMLInputElement>('[data-test=import-path]')!
    expect(field.getAttribute('role')).toBe('combobox')
    expect(field.getAttribute('aria-label')).toBe('Složka pro import')
    expect(field.value).toBe('~/')
    openDialog()!.querySelector<HTMLButtonElement>('[data-test="import-browse"]')!.click(); await flushPromises()
    expect(openDialog()).toBeNull()
    const browser = document.body.querySelector<HTMLElement>('[data-test="folder-browser"]')!
    expect(browser.textContent).toContain('/home/ada')
    browser.querySelector<HTMLButtonElement>('[data-test="browser-entry"]')!.click(); await flushPromises()
    browser.querySelector<HTMLButtonElement>('[data-test="browser-choose"]')!.click(); await flushPromises()
    expect(document.body.querySelector('[data-test="folder-browser"]')).toBeNull()
    expect(openDialog()!.querySelector<HTMLInputElement>('[data-test=import-path]')!.value).toBe('/home/ada/skills')
  })
  it('deletes the repo copy of an item only after confirmation; the item is inherited again', async () => {
    let copies = [{ repo: 'web', repo_name: 'Web', type: 'agent', name: 'agent-demo', same: false }]
    let blockers: { code: string; message: string }[] = []
    const plan = () => ({ action: 'remove', base: 'main', base_sha: 'b', digest: 'remove-digest', files: [{ path: '.factory/prompts/agent-demo/system.md', action: 'delete', diff: '', content: null, binary: false }], blockers })
    const mock = api((url) => {
      if (url === '/api/library/overrides') return envelope({ library: 'abc', overrides: copies, errors: [] })
      if (url === '/api/repos/web/factory/plan') return envelope(plan())
      if (url === '/api/repos/web/factory/apply') { copies = []; return envelope({ action: 'remove', commit: 'c0ffee1234' }) }
    })
    const applied = () => mock.mock.calls.filter(([url]) => url === '/api/repos/web/factory/apply')
    const wrapper = await openAgent()
    expect(wrapper.get('[data-test="override-count-agent-demo"]').text()).toBe('1')
    // blockers disable the confirmation
    blockers = [{ code: 'in_use', message: 'used by a workflow' }]
    await wrapper.get('[data-test="override-remove"]').trigger('click'); await flushPromises()
    expect(openDialog()!.querySelector<HTMLButtonElement>('[data-test="confirm-ok"]')!.disabled).toBe(true)
    await answerDialog(false)
    // cancel writes nothing
    blockers = []
    await wrapper.get('[data-test="override-remove"]').trigger('click'); await flushPromises()
    const ok = openDialog()!.querySelector<HTMLButtonElement>('[data-test="confirm-ok"]')!
    expect(ok.classList.contains('danger')).toBe(true)
    expect(openDialog()!.textContent).toContain('Smazat agent/agent-demo z repa Web?')
    expect(openDialog()!.textContent).toContain('.factory/prompts/agent-demo/system.md')
    expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/repos/web/factory/plan')![1]!.body))).toEqual({ action: 'remove', options: { type: 'agent', name: 'agent-demo' }, target: 'base' })
    await answerDialog(false)
    expect(applied()).toHaveLength(0)
    expect(wrapper.find('[data-test="override-web"]').exists()).toBe(true)
    // confirm deletes the copy
    await wrapper.get('[data-test="override-remove"]').trigger('click'); await flushPromises()
    await answerDialog(true)
    expect(applied()).toHaveLength(1)
    expect(JSON.parse(String(applied()[0]![1]!.body))).toEqual({ action: 'remove', options: { type: 'agent', name: 'agent-demo' }, target: 'base', digest: 'remove-digest' })
    expect(wrapper.text()).toContain('agent/agent-demo: kopie v repu Web smazána (c0ffee1), repo dědí z knihovny.')
    expect(wrapper.find('[data-test="override-web"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="item-no-overrides"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="override-count-agent-demo"]').text()).toBe('—')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('shows the sync state and pulls, pushes or connects a remote', async () => {
    let remote: string | null = null
    const mock = api((url) => {
      if (url === '/api/library' || url === '/api/library?fetch=1') return envelope({ exists: true, items, library: '/h/library', remote, branch: 'main', ahead: remote ? 0 : null, behind: remote ? 2 : null, dirty: false })
      if (url === '/api/library/remote') { remote = 'https://example.test/lib.git'; return envelope({ pushed: true }) }
      if (url === '/api/library/pull') return envelope({ pulled: 2 })
    })
    const wrapper = mount(LibrarySection, { props: { findings: [] } }); await flushPromises()
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
    // connect and pull are writes: the page checks the machine again
    expect(wrapper.emitted('changed')).toHaveLength(2)
  })
  it('shows the library findings of the machine check in the section', async () => {
    api()
    const finding = { code: 'library_dirty', scope: 'library' as const, severity: 'warning' as const, message: 'dirty', fix: 'commit it', action: null }
    const wrapper = mount(LibrarySection, { props: { findings: [finding] } }); await flushPromises()
    expect(wrapper.get('[data-test="library"] [data-test="machine-finding"]').text()).toContain('varování · library_dirty')
  })
  it('sets up a missing library in the section and hides the item browser', async () => {
    let ready = false
    const mock = api((url) => {
      if (url === '/api/library') return envelope(ready ? { exists: true, items } : { exists: false, default_url: 'https://example.test/team.git' })
      if (url === '/api/library/apply') { ready = true; return envelope({ commit: 'abc' }) }
    })
    const wrapper = mount(LibrarySection, { props: { findings: [] }, attachTo: document.body }); await flushPromises()
    expect(wrapper.find('[data-test="library-items"]').exists()).toBe(false)
    expect((wrapper.get('[data-test="library-url"]').element as HTMLInputElement).value).toBe('https://example.test/team.git')
    await wrapper.get('[data-test="library-init"]').trigger('click'); await flushPromises()
    expect(openDialog()?.textContent).toContain('IMPORT FILE CONTENT')
    await answerDialog(true)
    const call = mock.mock.calls.find(([url]) => url === '/api/library/apply')!
    expect(JSON.parse(call[1]!.body as string)).toEqual({ action: 'init', options: {}, digest: 'import-digest' })
    expect(wrapper.text()).toContain('Knihovna připravena')
    expect(wrapper.find('[data-test="library-items"]').exists()).toBe(true)
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('tells local changes, a pending pull request and a library in sync apart', async () => {
    const pr = { branch: 'haifa-library/20261013-abc', base: 'main', title: 'library: import skill/lint', created: 'now', repo: 'janbkrejci/HAIFA-LIBRARY', head_repo: 'ada/HAIFA-LIBRARY', url: 'https://github.com/janbkrejci/HAIFA-LIBRARY/pull/7', number: 7, state: 'OPEN', fork: true }
    let status: Record<string, unknown> = { ahead: 1, unsent: 1, pull_requests: [] }
    const mock = api((url) => {
      if (url === '/api/library' || url === '/api/library?fetch=1') return envelope({ exists: true, items, library: '/h/library', remote: 'https://github.com/janbkrejci/HAIFA-LIBRARY.git', branch: 'main', behind: 0, dirty: false, ...status })
      if (url === '/api/library/push') { status = { ahead: 1, unsent: 0, pull_requests: [pr] }; return envelope({ pushed: 1, pull_request: pr }) }
    })
    const wrapper = mount(LibrarySection, { props: { findings: [] } }); await flushPromises()
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

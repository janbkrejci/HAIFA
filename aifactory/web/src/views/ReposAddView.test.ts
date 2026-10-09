import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import ReposAddView from './ReposAddView.vue'
import { pendingInstall, installBusy, installCancelling, installCancelError } from '@/lib/factory'
import type { FsEntry, InspectResult, RepoFactory } from '@/lib/api'

const HOME = '/home/me'

function envelope(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

function failure(code: string, message = code, status = 400, data: unknown = null) {
  return new Response(
    JSON.stringify({ ok: false, data, error: { code, message, path: null, id: null, issues: [] }, warnings: [] }),
    { status },
  )
}

function factory(state: RepoFactory['state'], extra: Partial<RepoFactory> = {}): RepoFactory {
  return {
    repo: '/w/repo',
    base: 'main',
    commit: 'abc',
    state,
    action: null,
    sssf_leftover: false,
    alternate_rosters: false,
    onboarding: null,
    library: null,
    manifest_error: null,
    ...extra,
  }
}

function inspected(extra: Partial<InspectResult> = {}): InspectResult {
  return {
    path: '/w/repo',
    root: '/w/repo',
    subdir: null,
    registered: null,
    addable: true,
    problem: null,
    branch: 'main',
    remote: { name: 'origin', url: 'git@example.com:me/repo.git' },
    trace_db: '/w/repo/.factory/data/trace.db',
    factory: factory('pre_library'),
    ...extra,
  }
}

function problem(code: string, extra: Record<string, string> = {}): InspectResult {
  return inspected({
    addable: false,
    problem: { code, message: `server: ${code}`, ...extra },
    root: code === 'path_not_found' || code === 'not_git' ? null : '/w/repo',
    branch: null,
    remote: null,
    trace_db: null,
    factory: null,
  })
}

function dir(name: string, extra: Partial<FsEntry> = {}): FsEntry {
  return { name, path: `${HOME}/${name}`, is_git: false, has_factory: false, ...extra }
}

type Handler = (url: string, init?: RequestInit) => Response | undefined

interface Options {
  inspect?: InspectResult | ((body: { path: string }) => InspectResult | Response)
  dirs?: Record<string, FsEntry[]>
  pickAvailable?: boolean | 'error'
  handler?: Handler
}

function stub(options: Options = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const own = options.handler?.(url, init)
    if (own) return own
    if (url === '/api/repos/inspect') {
      const body = JSON.parse(String(init?.body)) as { path: string }
      const answer = typeof options.inspect === 'function' ? options.inspect(body) : (options.inspect ?? inspected())
      return answer instanceof Response ? answer : envelope(answer)
    }
    if (url === '/api/repos' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as { path: string }
      return envelope({ repo: { id: 'repo', name: 'repo', path: body.path }, created: true }, 201)
    }
    if (url.startsWith('/api/fs/dirs')) {
      const path = url.includes('?path=') ? decodeURIComponent(url.split('?path=')[1]) : HOME
      if (path.startsWith('/outside')) return failure('outside_home', 'outside', 403)
      const key = path.replace(/\/$/, '')
      const parent = key === HOME ? null : key.slice(0, key.lastIndexOf('/')) || '/'
      return envelope({ path: key, parent, entries: options.dirs?.[key] ?? [], truncated: false })
    }
    if (url === '/api/fs/pick' && !init) {
      if (options.pickAvailable === 'error') return failure('boom', 'boom', 500)
      return envelope({ available: options.pickAvailable ?? false })
    }
    return failure('unexpected', `unexpected ${url}`, 500)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function mountView() {
  const wrapper = mount(ReposAddView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

async function inspectPath(wrapper: Awaited<ReturnType<typeof mountView>>, path = '/w/repo') {
  await wrapper.get('[data-test="add-path"]').setValue(path)
  await wrapper.get('[data-test="add-inspect"]').trigger('click')
  await flushPromises()
}

function inspectCalls(fetchMock: ReturnType<typeof stub>): string[] {
  return fetchMock.mock.calls
    .filter(([url]) => url === '/api/repos/inspect')
    .map(([, init]) => (JSON.parse(String(init?.body)) as { path: string }).path)
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

enableAutoUnmount(afterEach)

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('ReposAddView', () => {
  it('prefills the path with ~/', async () => {
    stub()
    const wrapper = await mountView()
    expect((wrapper.get('[data-test="add-path"]').element as HTMLInputElement).value).toBe('~/')
    expect(wrapper.get('h1').text()).toBe('Přidat repozitář')
  })

  it('sends ~ unchanged to inspect', async () => {
    const fetchMock = stub()
    const wrapper = await mountView()
    await inspectPath(wrapper, '  ~/code/repo ')
    expect(inspectCalls(fetchMock)).toEqual(['~/code/repo'])
  })

  it('offers the installation wizard for a repo without factory', async () => {
    stub({ inspect: inspected({ factory: factory('none') }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.attributes('data-state')).toBe('none')
    const init = card.get('[data-test="inspect-init"]').text()
    expect(init).toContain('Pokračovat instalací')
    expect(card.find('[data-test="inspect-add"]').exists()).toBe(false)
  })

  it('warns about removing sssf and continues with a fresh installation', async () => {
    const fetchMock = stub({ inspect: inspected({ factory: factory('sssf') }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.find('[data-test="inspect-onboard"]').exists()).toBe(false)
    expect(card.get('[data-test="inspect-sssf-warning"]').text()).toContain('smazána')
    expect(card.get('[data-test="inspect-sssf-warning"]').text()).toContain('commitne')
    expect(card.find('[data-test="inspect-add"]').exists()).toBe(false)
    await card.get('[data-test="inspect-init"]').trigger('click')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([url, init]) => url === '/api/repos' && init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ path: '/w/repo', remove_sssf: true })
    expect(wrapper.get('h1').text()).toContain('instalace factory')
    pendingInstall.value = null
    installBusy.value = false
  })

  it.each(['pre_library', 'working_tree'] as const)('adds a %s repo by its root and emits its id', async (state) => {
    const fetchMock = stub({ inspect: inspected({ factory: factory(state) }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.get('[data-test="inspect-root"]').text()).toBe('/w/repo')
    expect(card.get('[data-test="inspect-branch"]').text()).toBe('main')
    expect(card.get('[data-test="inspect-remote"]').text()).toBe('git@example.com:me/repo.git')
    expect(card.get('[data-test="inspect-trace-db"]').text()).toBe('/w/repo/.factory/data/trace.db')
    expect(card.find('[data-test="inspect-working-tree"]').exists()).toBe(state === 'working_tree')
    await card.get('[data-test="inspect-add"]').trigger('click')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([url, init]) => url === '/api/repos' && init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ path: '/w/repo' })
    expect(wrapper.emitted('added')).toEqual([['repo']])
  })

  it('shows who, when and from what an onboarded repo came, and Add', async () => {
    const onboarding = {
      source: 'sssf' as const,
      source_commit: '0123456789abcdef',
      at: '2026-10-01T10:00:00+00:00',
      by: 'Ada',
      factory: '0.1.0',
      library_commit: null,
    }
    stub({ inspect: inspected({ factory: factory('onboarded', { onboarding }) }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.get('[data-test="inspect-state"]').text()).toBe('Onboardováno')
    const text = card.get('[data-test="inspect-onboarding"]').text()
    expect(text).toContain('Onboardoval Ada')
    expect(text).toContain('z převod ze sssf')
    expect(text).toContain('01234567')
    expect(card.find('[data-test="inspect-add"]').exists()).toBe(true)
  })

  it('offers Open for a registered repo and no Add: Backlog when onboarded, else Factory', async () => {
    stub({ inspect: inspected({ registered: 'repo', factory: factory('onboarded') }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.text()).toContain('Repo už je v dashboardu.')
    expect(card.get('[data-test="inspect-open"]').attributes('href')).toBe('#/r/repo/backlog')
    expect(card.find('[data-test="inspect-add"]').exists()).toBe(false)
    expect(card.find('[data-test="inspect-init"]').exists()).toBe(false)
  })

  it('opens the Factory tab of a registered repo without factory and offers its install', async () => {
    stub({ inspect: inspected({ registered: 'repo', factory: factory('none') }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.get('[data-test="inspect-open"]').attributes('href')).toBe('#/r/repo/factory')
    await card.get('[data-test="inspect-init"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="factory-operation"]').exists()).toBe(true)
    expect(pendingInstall.value).toEqual({ id: 'repo', created: true })
    pendingInstall.value = null
  })

  it('stays on the page after adding: a card opens the repo or clears the form for another', async () => {
    stub({ inspect: inspected({ factory: factory('working_tree') }) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    await wrapper.get('[data-test="inspect-add"]').trigger('click')
    await flushPromises()
    const card = wrapper.get('[data-test="repo-added"]')
    expect(card.text()).toContain('Repozitář repo přidán')
    expect(card.get('[data-test="repo-added-open"]').attributes('href')).toBe('#/r/repo/factory')
    expect(wrapper.find('a[href="#/overview"]').exists()).toBe(true)
    await card.get('[data-test="repo-added-another"]').trigger('click')
    expect(wrapper.find('[data-test="repo-added"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="inspect-card"]').exists()).toBe(false)
    expect((wrapper.get('[data-test="add-path"]').element as HTMLInputElement).value).toBe('~/')
  })

  it.each([
    ['path_not_found', 'Složka neexistuje.'],
    ['not_a_directory', 'Cesta nevede ke složce.'],
    ['not_git', 'HAIFA nespouští git init'],
    ['run_worktree', 'worktree běhu úkolu'],
    ['bare_repo', 'Holé repo'],
    ['no_commits', 'nemá žádný commit'],
    ['linked_worktree', 'propojený worktree'],
    ['trace_db_shared', 'už používá registrované repo other'],
    ['something_new', 'server: something_new'],
  ])('rejects %s with its reason and no Add', async (code, reason) => {
    const extra: Record<string, string> = code === 'trace_db_shared' ? { repo: 'other' } : {}
    stub({ inspect: problem(code, extra) })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    const card = wrapper.get('[data-test="inspect-card"]')
    expect(card.attributes('data-state')).toBe('problem')
    expect(card.get('[data-test="inspect-problem"]').text()).toContain(reason)
    expect(card.find('[data-test="inspect-add"]').exists()).toBe(false)
  })

  it('inspects the main checkout of a linked worktree on request', async () => {
    const fetchMock = stub({
      inspect: (body) =>
        body.path === '/w/wt' ? problem('linked_worktree', { main_checkout: '/w/main' }) : inspected({ path: '/w/main', root: '/w/main' }),
    })
    const wrapper = await mountView()
    await inspectPath(wrapper, '/w/wt')
    expect(wrapper.get('[data-test="inspect-problem"]').text()).toContain('/w/main')
    await wrapper.get('[data-test="use-main-checkout"]').trigger('click')
    await flushPromises()
    expect(inspectCalls(fetchMock)).toEqual(['/w/wt', '/w/main'])
    expect((wrapper.get('[data-test="add-path"]').element as HTMLInputElement).value).toBe('/w/main')
    expect(wrapper.get('[data-test="inspect-root"]').text()).toBe('/w/main')
  })

  it('says the repo root is used for a subfolder', async () => {
    stub({ inspect: inspected({ path: '/w/repo/src', subdir: 'src' }) })
    const wrapper = await mountView()
    await inspectPath(wrapper, '/w/repo/src')
    expect(wrapper.get('[data-test="inspect-subdir"]').text()).toBe('Použije se kořen repozitáře /w/repo.')
  })

  it('explains a usage error of a relative path', async () => {
    stub({ inspect: () => failure('usage_error', 'path must be absolute', 400) })
    const wrapper = await mountView()
    await inspectPath(wrapper, 'code/repo')
    expect(wrapper.get('[data-test="inspect-error"]').text()).toBe('Zadej absolutní cestu nebo cestu začínající ~.')
    expect(wrapper.find('[data-test="inspect-card"]').exists()).toBe(false)
  })

  it('shows an add error on the card', async () => {
    stub({
      handler: (url, init) =>
        url === '/api/repos' && init?.method === 'POST' ? failure('trace_db_shared', 'shared', 409, { repo: 'other' }) : undefined,
    })
    const wrapper = await mountView()
    await inspectPath(wrapper)
    await wrapper.get('[data-test="inspect-add"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="inspect-add-error"]').text()).toContain('už používá registrované repo other')
    expect(wrapper.emitted('added')).toBeUndefined()
  })

  it('suggests subfolders of the typed folder with git and factory tags', async () => {
    const fetchMock = stub({
      dirs: {
        [HOME]: [dir('code', { is_git: true, has_factory: true }), dir('docs'), dir('cold')],
        [`${HOME}/code`]: [dir('code/app')],
      },
    })
    const wrapper = await mountView()
    const field = wrapper.get('[data-test="add-path"]')
    await field.setValue('~/co')
    await wait(200)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(`/api/fs/dirs?path=${encodeURIComponent(`${HOME}/`)}`)
    const items = wrapper.findAll('[data-test="path-suggestion"]')
    expect(items.map((i) => i.text().split('/')[0])).toEqual(['code', 'cold'])
    expect(items[0].find('[data-test="tag-git"]').exists()).toBe(true)
    expect(items[0].find('[data-test="tag-factory"]').exists()).toBe(true)
    expect(items[1].find('[data-test="tag-git"]').exists()).toBe(false)
    await items[0].trigger('mousedown')
    await flushPromises()
    expect((field.element as HTMLInputElement).value).toBe('~/code/')
  })

  it('picks a suggestion with the arrows and Enter, and Enter alone inspects', async () => {
    const fetchMock = stub({ dirs: { [HOME]: [dir('code'), dir('cold')] } })
    const wrapper = await mountView()
    const field = wrapper.get('[data-test="add-path"]')
    await field.setValue('~/co')
    await wait(200)
    await flushPromises()
    await field.trigger('keydown', { key: 'ArrowDown' })
    await field.trigger('keydown', { key: 'ArrowDown' })
    await field.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect((field.element as HTMLInputElement).value).toBe('~/cold/')
    expect(inspectCalls(fetchMock)).toEqual([])
    await field.trigger('keydown', { key: 'Escape' })
    await field.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(inspectCalls(fetchMock)).toEqual(['~/cold/'])
  })

  it('shows no suggestions when the folder cannot be listed', async () => {
    stub()
    const wrapper = await mountView()
    await wrapper.get('[data-test="add-path"]').setValue('/outside/x')
    await wait(200)
    await flushPromises()
    expect(wrapper.find('[data-test="path-suggestions"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="inspect-error"]').exists()).toBe(false)
  })

  it.each([
    [true, true],
    [false, false],
    ['error' as const, false],
  ])('shows the Finder button when available is %s: %s', async (available, shown) => {
    stub({ pickAvailable: available })
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="add-pick"]').exists()).toBe(shown)
  })

  it('inspects the folder picked in the system dialog and nothing when cancelled', async () => {
    let answer: unknown = { cancelled: true }
    const fetchMock = stub({
      pickAvailable: true,
      handler: (url, init) => (url === '/api/fs/pick' && init?.method === 'POST' ? envelope(answer) : undefined),
    })
    const wrapper = await mountView()
    await wrapper.get('[data-test="add-pick"]').trigger('click')
    await flushPromises()
    expect(inspectCalls(fetchMock)).toEqual([])
    answer = { path: '/w/repo' }
    await wrapper.get('[data-test="add-pick"]').trigger('click')
    await flushPromises()
    expect(inspectCalls(fetchMock)).toEqual(['/w/repo'])
    expect(wrapper.find('[data-test="inspect-card"]').exists()).toBe(true)
  })

  it('says the system dialog is already open', async () => {
    stub({
      pickAvailable: true,
      handler: (url, init) =>
        url === '/api/fs/pick' && init?.method === 'POST' ? failure('picker_busy', 'busy', 409) : undefined,
    })
    const wrapper = await mountView()
    await wrapper.get('[data-test="add-pick"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="pick-error"]').text()).toBe('Dialog výběru složky už je otevřený.')
  })

  it('browses folders from home and inspects the chosen one', async () => {
    const fetchMock = stub({
      dirs: { [HOME]: [dir('code', { is_git: true })], [`${HOME}/code`]: [] },
    })
    const wrapper = await mountView()
    await wrapper.get('[data-test="add-browse"]').trigger('click')
    await flushPromises()
    const browser = () => document.body.querySelector<HTMLElement>('[data-test="folder-browser"]')
    expect(browser()?.querySelector('[data-test="browser-path"]')?.textContent).toBe(HOME)
    expect(browser()?.querySelector('[data-test="tag-git"]')).not.toBeNull()
    browser()?.querySelector<HTMLButtonElement>('[data-test="browser-entry"]')?.click()
    await flushPromises()
    expect(browser()?.querySelector('[data-test="browser-path"]')?.textContent).toBe(`${HOME}/code`)
    browser()?.querySelector<HTMLButtonElement>('[data-test="browser-choose"]')?.click()
    await flushPromises()
    expect(browser()).toBeNull()
    expect((wrapper.get('[data-test="add-path"]').element as HTMLInputElement).value).toBe(`${HOME}/code`)
    expect(inspectCalls(fetchMock)).toEqual([`${HOME}/code`])
  })
})


describe('temporary installation registration', () => {
  afterEach(() => { pendingInstall.value = null; installBusy.value = false; installCancelling.value = false; installCancelError.value = null })
  it.each([true, false])('cancels created=%s without applying or removing an existing registration', async created => {
    const fetchMock = stub({ inspect: inspected({ factory: factory('none') }), handler: (url, init) => {
      if (url === '/api/repos' && init?.method === 'POST') return envelope({ repo: { id: 'temporary' }, created })
      if (init?.method === 'DELETE') return envelope({ removed: {} })
    } })
    const w = await mountView(); await inspectPath(w)
    await w.get('[data-test="inspect-init"]').trigger('click'); await flushPromises()
    expect(w.find('[data-test="factory-operation"]').exists()).toBe(true)
    await w.get('[data-test="cancel-install"]').trigger('click'); await flushPromises()
    const deletions = fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')
    expect(deletions).toHaveLength(created ? 1 : 0)
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/factory/apply'))).toBe(false)
    expect(pendingInstall.value).toBeNull()
  })
  it('retains ownership and exposes retry if unregistering fails', async () => {
    let refusal = true
    stub({ inspect: inspected({ factory: factory('none') }), handler: (_url, init) => {
      if (init?.method === 'DELETE') return refusal ? failure('busy', 'cannot unregister') : envelope({ removed: {} })
    } })
    const w = await mountView(); await inspectPath(w)
    await w.get('[data-test="inspect-init"]').trigger('click'); await flushPromises()
    await w.get('[data-test="cancel-install"]').trigger('click'); await flushPromises()
    expect(w.text()).toContain('cannot unregister')
    expect(pendingInstall.value).not.toBeNull()
    refusal = false
    await w.get('[data-test="cancel-install"]').trigger('click'); await flushPromises()
    expect(pendingInstall.value).toBeNull()
  })
})


it.each([['onboarded_in_remote', 'Onboardováno na remote'], ['onboarding_pending', 'Čeká v PR']] as const)('labels known onboarding state %s', async (onboarding_state, label) => {
  stub({ inspect: inspected({ factory: factory('sssf', { onboarding_state }) }) })
  const wrapper = await mountView()
  await inspectPath(wrapper)
  expect(wrapper.get('[data-test="inspect-state"]').text()).toBe(label)
})

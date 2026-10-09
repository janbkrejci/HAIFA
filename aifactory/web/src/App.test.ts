import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import App from './App.vue'
import { resetConfigStatusForTests } from './lib/configStatus'
import { CLEAN_STATUS, DIRTY_STATUS } from './test/settingsFixtures'
import { runsResponse, summary } from './test/runsFixtures'
import { FakeEventSource, filesEvent } from './test/fakeEventSource'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from './lib/live'
import { nameTip, resetNamesForTests } from './lib/names'
import { resetBacklogStatusForTests } from './lib/backlogStatus'
import type { RepoItem } from './lib/api'
import { failed, overview, repo as ovRepo, review, running } from './test/overviewFixtures'
import { answerDialog, openDialog } from './test/modal'
import { installPlan, factoryCheck } from './test/factoryFixtures'
import { deferred } from './test/deferred'
import { pendingInstall, installBusy, installRegistering, installCancelError, lastFactoryResult } from './lib/factory'

function envelope(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

const HEALTH = { app: 'haifa-dashboard', version: '0.1.0', home: '/home/me/.haifa' }

function repo(id: string, name: string, path: string, status: RepoItem['status'] = 'ok'): RepoItem {
  return { id, name, path, added_at: '2026-10-01T10:00:00+00:00', status, factory: null }
}

const HAIFA = repo('haifa', 'HAIFA', '/work/HAIFA')
const OTHER = repo('other', 'Other', '/work/apps/Other')

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined

/**
 * /api/health and /api/repos are global; /api/repos/<id>/config/status answers `status`
 * (clean by default); every other repo endpoint (the Backlog screen) an empty backlog.
 */
function stubApi(
  options: { repos?: RepoItem[]; status?: unknown; handler?: Handler } = {},
) {
  const repos = options.repos ?? [HAIFA]
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const own = options.handler?.(url, init)
    if (own) return own
    if (url.startsWith('/api/updates')) return envelope({ status: 'current', current_version: '0.1.0' })
    if (url.startsWith('/api/machine/check')) return envelope({ ok: true, findings: [] })
    if (url === '/api/library') return envelope({ exists: true, items: [] })
    if (url === '/api/health') return envelope(HEALTH)
    if (url === '/api/repos') return envelope({ repos, home: HEALTH.home })
    if (url === '/api/code') return envelope({ stale: false, started: 'a', current: 'a' })
    if (url.endsWith('/config/status')) return envelope(options.status ?? CLEAN_STATUS)
    return envelope({ levels: ['module', 'step', 'task'], items: [], tasks: [] })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

// a failed test must not leave a mounted App reacting to the next test's hash
enableAutoUnmount(afterEach)

afterEach(() => {
  pendingInstall.value = null
  installBusy.value = false
  installRegistering.value = false
  installCancelError.value = null
  lastFactoryResult.value = null
  vi.unstubAllGlobals()
  resetConfigStatusForTests()
  resetBacklogStatusForTests()
  resetLiveForTests()
  FakeEventSource.reset()
  resetNamesForTests()
  document.body.innerHTML = ''
})

describe('App', () => {
  it('reads the server system check on startup without forcing new probes', async () => {
    const fetchMock = stubApi()
    go('#/overview')
    const wrapper = mount(App)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check')
    expect(fetchMock).not.toHaveBeenCalledWith('/api/machine/check?fresh=1')
    wrapper.unmount()
  })
  it('refreshes the registered repo state after a Factory operation and removes its listener on unmount', async () => {
    const repos = [HAIFA]
    const fetchMock = stubApi({ repos })
    go('#/r/haifa/backlog')
    const wrapper = mount(App); await flushPromises()
    const before = fetchMock.mock.calls.filter(([url]) => url === '/api/repos').length
    repos[0] = { ...HAIFA, name: 'Installed HAIFA', factory: { state: 'onboarded' } }
    window.dispatchEvent(new Event('factory-applied')); await flushPromises()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/repos')).toHaveLength(before + 2)
    expect(document.title).toBe('Installed HAIFA · Backlog · HAIFA')
    wrapper.unmount()
    window.dispatchEvent(new Event('factory-applied')); await flushPromises()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/repos')).toHaveLength(before + 2)
  })
  it('waits for temporary registration cleanup before internal navigation', async () => {
    const deletion = deferred<Response>()
    const fetchMock = stubApi({ handler: (url, init) => {
      if (url === '/api/repos/haifa' && init?.method === 'DELETE') return deletion.promise
      if (url.endsWith('/factory/plan')) return envelope(installPlan())
      if (url === '/api/overview') return envelope(overview([ovRepo('haifa')]))
    } })
    go('#/repos/add')
    pendingInstall.value = { id: 'haifa', created: true }
    const wrapper = mount(App); await flushPromises()
    go('#/overview'); await flushPromises()
    expect(wrapper.find('[data-test="cancel-install"]').exists()).toBe(true)
    expect(pendingInstall.value?.id).toBe('haifa')
    deletion.resolve(envelope({ removed: { id: 'haifa' } })); await flushPromises()
    expect(pendingInstall.value).toBeNull()
    expect(wrapper.find('[data-test="cancel-install"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toHaveLength(1)
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/factory/apply'))).toBe(false)
  })
  it('retains successful installation registration and offers its Factory page after refreshing repos', async () => {
    const fetchMock = stubApi({ handler: (url) => {
      if (url.endsWith('/factory/plan')) return envelope(installPlan())
      if (url.endsWith('/factory/apply')) return envelope({ commit: 'installed' })
      if (url.includes('/factory/check')) return envelope(factoryCheck())
      if (url === '/api/overview') return envelope(overview([ovRepo('haifa')]))
    } })
    go('#/repos/add')
    pendingInstall.value = { id: 'haifa', created: true }
    const wrapper = mount(App, { attachTo: document.body }); await flushPromises()
    await wrapper.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    await flushPromises(); go(window.location.hash); await flushPromises()
    expect(pendingInstall.value).toBeNull()
    expect(window.location.hash).toBe('#/repos/add')
    expect(wrapper.get('[data-test="repo-added-open"]').attributes('href')).toBe('#/r/haifa/factory')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/repos').length).toBeGreaterThan(1)
    expect(wrapper.get('[data-test="repo-added"]').text()).toContain('Repozitář haifa přidán')
  })
  it('opens a config commit preview from the banner and refreshes check/status/repos only after confirmation', async () => {
    let applied = false
    const fetchMock = stubApi({ handler: (url, init) => {
      if (url.endsWith('/config/status')) return envelope(applied ? CLEAN_STATUS : DIRTY_STATUS)
      if (url.includes('/factory/check')) return envelope(factoryCheck())
      if (url.endsWith('/factory/plan')) return envelope({ ...installPlan(), action: 'config_commit' })
      if (url.endsWith('/factory/apply')) { applied = true; return envelope({ commit: 'config-commit' }) }
      if (url === '/api/overview') return envelope(overview([ovRepo('haifa')]))
      if (init?.method === 'DELETE') throw new Error('unexpected delete')
    } })
    go('#/r/haifa/backlog')
    const wrapper = mount(App, { attachTo: document.body }); await flushPromises()
    await wrapper.get('[data-test="config-commit"]').trigger('click')
    go(window.location.hash); await flushPromises()
    expect(wrapper.find('[data-test="factory-plan"]').exists()).toBe(true)
    const request = fetchMock.mock.calls.find(([url]) => url.endsWith('/factory/plan'))!
    expect(JSON.parse(request[1]!.body as string).action).toBe('config_commit')
    expect(applied).toBe(false)
    await wrapper.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(false)
    expect(applied).toBe(false)
    await wrapper.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true); await flushPromises()
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/factory/check?fresh=1'))).toBe(true)
    expect(wrapper.get('[data-test="factory-success"] a').attributes('href')).toBe('#/r/haifa/backlog')
  })
  it('shows the five screens of the repo in the navigation', async () => {
    stubApi()
    const wrapper = mount(App)
    await flushPromises()
    const links = wrapper.findAll('nav a')
    expect(links.map((a) => a.text())).toEqual(['Backlog', 'Běhy', 'Review', 'Factory', 'Nastavení'])
    expect(links.map((a) => a.attributes('href'))).toEqual([
      '#/r/haifa/backlog',
      '#/r/haifa/runs',
      '#/r/haifa/review',
      '#/r/haifa/factory',
      '#/r/haifa/settings',
    ])
    wrapper.unmount()
  })

  it('switches screens on hashchange', async () => {
    stubApi()
    const wrapper = mount(App)
    await flushPromises()
    go('#/r/haifa/runs')
    await flushPromises()
    expect(wrapper.find('nav a.active').text()).toBe('Běhy')
    expect(wrapper.find('main h1').text()).toBe('Běhy')
    wrapper.unmount()
  })

  it('titles the page by repo and screen', async () => {
    stubApi()
    go('#/r/haifa/runs')
    const wrapper = mount(App)
    await flushPromises()
    expect(document.title).toBe('HAIFA · Běhy · HAIFA')
    go('#/overview')
    await flushPromises()
    expect(document.title).toBe('Přehled · HAIFA')
    go('#/repos/add')
    await flushPromises()
    expect(document.title).toBe('Přidat repozitář · HAIFA')
    wrapper.unmount()
  })

  it('shows the current repo and the version in the switcher', async () => {
    stubApi()
    const wrapper = mount(App)
    await flushPromises()
    const switcher = wrapper.get('[data-test="repo-switcher"]')
    expect(switcher.classes()).toContain('repo-switcher')
    expect(switcher.get('[data-test="switcher-current"]').text()).toBe('HAIFA')
    expect(switcher.text()).toContain('v0.1.0')
    expect(wrapper.find('.repo-chip').exists()).toBe(false)
    wrapper.unmount()
  })

  it('lists the overview, the repos and the repo pages in the switcher, keeping the screen', async () => {
    const repos = [
      HAIFA,
      repo('sandbox', 'sandbox', '/work/play/sandbox', 'not_installed'),
      repo('gone', 'gone', 'C:\\old\\gone', 'missing'),
    ]
    stubApi({ repos })
    go('#/r/haifa/review/M01-S01-T01')
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    await wrapper.get('[data-test="switcher-button"]').trigger('click')
    await flushPromises()
    const menu = wrapper.get('[data-test="switcher-menu"]')
    const label = (a: ReturnType<typeof menu.get>) =>
      a.find('.repo-name').exists() ? a.get('.repo-name').text() : a.text()
    expect(menu.findAll('a').map(label)).toEqual([
      'Přehled',
      'Tento počítač',
      'Knihovna',
      'HAIFA',
      'sandbox',
      'gone',
      'Přidat repozitář…',
    ])
    expect(menu.get('[data-test="switch-overview"]').attributes('href')).toBe('#/overview')
    const sandbox = menu.get('[data-test="switch-repo-sandbox"]')
    expect(sandbox.attributes('href')).toBe('#/r/sandbox/review')
    expect(sandbox.get('[data-test="repo-parent"]').text()).toBe('/work/play')
    expect(sandbox.get('[data-test="repo-label"]').text()).toBe('nenainstalováno')
    const gone = menu.get('[data-test="switch-repo-gone"]')
    expect(gone.get('[data-test="repo-label"]').text()).toBe('chybí')
    expect(gone.get('[data-test="repo-parent"]').text()).toBe('C:\\old')
    expect(menu.get('[data-test="switch-repo-haifa"]').find('[data-test="repo-label"]').exists()).toBe(false)
    expect(menu.get('[data-test="switch-add"]').text()).toBe('Přidat repozitář…')
    expect(menu.get('[data-test="switch-add"]').attributes('href')).toBe('#/repos/add')
    expect(menu.find('[data-test="switch-manage"]').exists()).toBe(false)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-test="switcher-menu"]').exists()).toBe(false)
    await wrapper.get('[data-test="switcher-button"]').trigger('click')
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[data-test="switcher-menu"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('remounts the screen and its config banner on a repo switch', async () => {
    const otherRuns = { runs: [summary({ run_id: 'r-other', task_title: 'Other task' })] }
    const fetchMock = stubApi({
      repos: [HAIFA, OTHER],
      handler: (url) => {
        if (url === '/api/repos/haifa/config/status') return envelope(DIRTY_STATUS)
        if (url === '/api/repos/other/config/status') return envelope(CLEAN_STATUS)
        if (url === '/api/repos/haifa/runs') return envelope(runsResponse())
        if (url === '/api/repos/other/runs') return envelope(otherRuns)
        return undefined
      },
    })
    go('#/r/haifa/runs')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('tr[data-run="r-ok"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(true)

    go('#/r/other/runs')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/other/runs')
    expect(wrapper.find('tr[data-run="r-ok"]').exists()).toBe(false)
    expect(wrapper.find('tr[data-run="r-other"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="switcher-current"]').text()).toBe('Other')
    expect(wrapper.findAll('nav a').map((a) => a.attributes('href'))[0]).toBe('#/r/other/backlog')

    go('#/r/haifa/runs')
    await flushPromises()
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps a late config answer of the previous repo out of the new one', async () => {
    let answer: ((r: Response) => void) | null = null
    stubApi({ repos: [HAIFA, OTHER] })
    const base = globalThis.fetch as unknown as (url: string, init?: RequestInit) => Promise<Response>
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) =>
        url === '/api/repos/haifa/config/status'
          ? new Promise<Response>((resolve) => {
              answer = resolve
            })
          : base(url, init),
      ),
    )
    const wrapper = mount(App)
    await flushPromises()
    go('#/r/other/backlog')
    await flushPromises()
    answer!(envelope(DIRTY_STATUS))
    await flushPromises()
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('gives the theme toggle an accessible name and a custom tooltip', async () => {
    stubApi()
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    const toggle = wrapper.find('.theme-toggle')
    expect(toggle.attributes('title')).toBeUndefined()
    expect(toggle.attributes('aria-label')).toMatch(/Přepnout na (světlý|tmavý) motiv/)
    await toggle.trigger('focusin')
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')
    expect(tip?.textContent).toContain(toggle.attributes('aria-label'))
    expect(tip?.parentElement).toBe(document.body)
    expect(wrapper.find('[title]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reports an unreachable API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('.api-down').text()).toBe('API nedostupné')
    wrapper.unmount()
  })

  it('shows no config banner when .factory/ is committed', async () => {
    stubApi()
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the uncommitted config banner on every screen', async () => {
    stubApi({ status: DIRTY_STATUS })
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[data-test="config-banner"]').text()).toContain('main')
    expect(wrapper.findAll('[data-test="config-change"]')).toHaveLength(2)
    go('#/r/haifa/runs')
    await flushPromises()
    expect(wrapper.find('main h1').text()).toBe('Běhy')
    expect(wrapper.find('[data-test="config-banner"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows the uncommitted backlog with a button that commits it all', async () => {
    let clean = false
    const fetchMock = stubApi({
      handler: (url) => {
        if (url === '/api/repos/haifa/backlog/status')
          return envelope({
            base: 'main',
            commit: 'abcdef1234',
            clean,
            changes: clean ? [] : [{ path: 'backlog/HAIFA/index.md', status: 'modified' }],
          })
        if (url === '/api/repos/haifa/backlog/commit') {
          clean = true
          return envelope({ committed: true, commit: 'f00', base: 'main', paths: [], pushed: false })
        }
        return undefined
      },
    })
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[data-test="backlog-change"]').text()).toBe('modified backlog/HAIFA/index.md')
    await wrapper.get('[data-test="backlog-commit"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/commit', expect.objectContaining({ method: 'POST' }))
    expect(wrapper.find('[data-test="backlog-banner"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reloads the names of codes on a live change of the backlog', async () => {
    let title = 'Schema'
    stubApi({
      handler: (url) =>
        url === '/api/repos/haifa/backlog/names'
          ? envelope({ levels: ['project', 'step', 'task'], names: { 'M01-S01-T01': { title, level: 'task' } } })
          : undefined,
    })
    vi.stubGlobal('EventSource', FakeEventSource)
    const wrapper = mount(App)
    await flushPromises()
    expect(FakeEventSource.latest().url).toBe('/api/repos/haifa/live')
    expect(nameTip('M01-S01-T01')).toBe('Task: Schema')
    title = 'Schema v2'
    FakeEventSource.latest().emit('files', filesEvent(['backlog/M01-core/S01-model/M01-S01-T01-schema.md']))
    await new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
    await flushPromises()
    expect(nameTip('M01-S01-T01')).toBe('Task: Schema v2')
    wrapper.unmount()
  })

  it('opens the live stream of the new repo after a switch', async () => {
    stubApi({ repos: [HAIFA, OTHER] })
    vi.stubGlobal('EventSource', FakeEventSource)
    const wrapper = mount(App)
    await flushPromises()
    const first = FakeEventSource.latest()
    go('#/r/other/backlog')
    await flushPromises()
    expect(first.closed).toBe(true)
    expect(FakeEventSource.latest().url).toBe('/api/repos/other/live')
    expect(FakeEventSource.latest().closed).toBe(false)
    wrapper.unmount()
  })

  it.each([
    [false, true], [true, false], [true, true],
  ])('first start with check ok=%s and library exists=%s stays on the overview with the guide', async (ok, exists) => {
    stubApi({ repos: [], handler: url => {
      if (url.startsWith('/api/machine/check')) return envelope({ ok, findings: [], checked_at: 'now' })
      if (url === '/api/library') return envelope({ exists, items: [] })
      return undefined
    } })
    go('#/overview')
    const wrapper = mount(App)
    await flushPromises()
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await flushPromises()
    expect(window.location.hash).toBe('#/overview')
    expect(wrapper.find('[data-test="repo-page"]').exists()).toBe(false)
    const warning = wrapper.get('[data-test="readiness-warning"]')
    expect(warning.attributes('href')).toBe('#/problems')
    go('#/problems')
    await flushPromises()
    expect(wrapper.get('[data-test="system-problems"]').findAll('a').some(a => a.attributes('href') === (ok && exists ? '#/repos/add' : '#/setup'))).toBe(true)
    wrapper.unmount()
  })

  it('shows how to add a repo when there is none', async () => {
    stubApi({ repos: [] })
    go('#/overview')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('nav').exists()).toBe(false)
    expect(wrapper.find('[data-test="limits"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="readiness-warning"]').text()).toBe('Nalezeny problémy')
    expect(wrapper.get('[data-test="readiness-warning"]').attributes('href')).toBe('#/problems')
    expect(wrapper.find('[data-test="repo-page"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="switcher-current"]').text()).toBe('Přehled')
    wrapper.unmount()
  })

  it('shows the overview cards and lists the repos with a link to open them', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    stubApi({
      repos: [HAIFA, repo('sandbox', 'sandbox', '/work/sandbox')],
      handler: (url) => {
        if (url.endsWith('/factory/roster')) return envelope({ agents: [{ name: 'builder' }] })
        if (url.endsWith('/backlog')) return envelope({ items: [{ id: 'M01' }] })
        if (url === '/api/overview') return envelope(overview([ovRepo('haifa', { name: 'HAIFA', running: [running()] }), ovRepo('sandbox')]))
      },
    })
    go('#/overview')
    const wrapper = mount(App)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(3000)
    expect(wrapper.get('main h1').text()).toBe('Přehled')
    expect(wrapper.get('[data-test="overview-card"]').attributes('data-repo')).toBe('haifa')
    expect(wrapper.get('[data-test="row-running"]').attributes('href')).toBe('#/r/haifa/runs/run-1')
    expect(wrapper.get('[data-test="calm-repo"]').attributes('data-repo')).toBe('sandbox')
    go('#/repos')
    await flushPromises()
    expect(window.location.hash).toBe('#/overview')
    expect(wrapper.find('[data-test="repo-row"]').exists()).toBe(false)
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('shows the running, review and failed counts of each repo in the switcher on opening', async () => {
    let calls = 0
    const fetchMock = stubApi({
      repos: [HAIFA, OTHER],
      handler: (url) => {
        if (url !== '/api/overview') return undefined
        calls += 1
        return envelope(
          overview([
            ovRepo('haifa', {
              running: [running(), running({ run_id: 'run-2' })],
              review: [review()],
              failed: [failed()],
            }),
            ovRepo('other'),
          ]),
        )
      },
    })
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    expect(calls).toBe(0)
    await wrapper.get('[data-test="switcher-button"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/overview')
    const haifa = wrapper.get('[data-test="switch-repo-haifa"]')
    expect(haifa.get('[data-test="count-running"]').text()).toBe('2')
    expect(haifa.get('[data-test="count-running"]').attributes('aria-label')).toBe('2 běží')
    expect(haifa.get('[data-test="count-review"]').text()).toBe('1')
    expect(haifa.get('[data-test="count-failed"]').text()).toBe('1')
    const other = wrapper.get('[data-test="switch-repo-other"]')
    expect(other.find('[data-test="count-running"]').exists()).toBe(false)
    expect(other.find('[data-test="count-failed"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the limits on global pages from /api/limits and on a repo page from the repo', async () => {
    const providers = [{ harness: 'claude', label: 'Claude', error: null, windows: [{ id: '5h', label: '5h', used: 10, left: 90, resets_at: null }] }]
    const fetchMock = stubApi({ handler: (url) => (url.endsWith('/limits') ? envelope({ providers }) : undefined) })
    go('#/setup')
    const wrapper = mount(App)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/limits')
    expect(wrapper.find('[data-test="limits"]').exists()).toBe(true)
    go('#/r/haifa/backlog')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/limits')
    wrapper.unmount()
  })

  it('shows the add page', async () => {
    stubApi()
    go('#/repos/add')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('main h1').text()).toBe('Přidat repozitář')
    expect(wrapper.find('[data-test="add-path"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="add-inspect"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('stays on the add page with a link to the added repo, after reloading the repos', async () => {
    const NEW = repo('new-repo', 'new-repo', '/work/new-repo', 'uncommitted')
    let added = false
    const fetchMock = stubApi({
      handler: (url, init) => {
        if (url === '/api/repos' && init?.method === 'POST') {
          added = true
          return envelope({ repo: NEW, created: true })
        }
        if (url === '/api/repos') return envelope({ repos: added ? [HAIFA, NEW] : [HAIFA], home: HEALTH.home })
        if (url === '/api/repos/inspect') {
          return envelope({
            path: '/work/new-repo',
            root: '/work/new-repo',
            subdir: null,
            registered: null,
            addable: true,
            problem: null,
            branch: 'main',
            remote: null,
            trace_db: '/work/new-repo/.factory/data/trace.db',
            factory: { repo: '/work/new-repo', base: 'main', commit: 'abc', state: 'pre_library', action: null,
              sssf_leftover: false, alternate_rosters: false, onboarding: null, library: null, manifest_error: null },
          })
        }
        if (url.startsWith('/api/fs/')) return envelope({ path: '/home/me', parent: null, entries: [], truncated: false, available: false })
        if (url.includes('/factory/check')) return envelope(null)
        return undefined
      },
    })
    go('#/repos/add')
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-test="add-path"]').setValue('/work/new-repo')
    await wrapper.get('[data-test="add-inspect"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="inspect-add"]').trigger('click')
    await flushPromises()
    expect(window.location.hash).toBe('#/repos/add')
    expect(wrapper.get('[data-test="repo-added"]').text()).toContain('Repozitář new-repo přidán')
    expect(wrapper.get('[data-test="repo-added-open"]').attributes('href')).toBe('#/r/new-repo/factory')
    const listCalls = fetchMock.mock.calls.filter(([u, i]) => u === '/api/repos' && !i)
    expect(listCalls.length).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })

  it('offers removing a repo whose folder is missing, then goes to the overview', async () => {
    const GONE = repo('gone', 'gone', '/work/gone', 'missing')
    let removed = false
    const fetchMock = stubApi({
      repos: [HAIFA, GONE],
      handler: (url, init) => {
        if (url === '/api/repos/gone' && init?.method === 'DELETE') {
          removed = true
          return envelope({ removed: { id: 'gone' } })
        }
        if (url === '/api/repos') return envelope({ repos: removed ? [HAIFA] : [HAIFA, GONE], home: HEALTH.home })
        if (url === '/api/overview') return envelope(overview([ovRepo('haifa', { name: 'HAIFA' })]))
        return undefined
      },
    })
    go('#/r/gone/backlog')
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('main h1').text()).toBe('Složka repozitáře gone chybí')
    await wrapper.get('[data-test="missing-remove"]').trigger('click')
    await flushPromises()
    expect(openDialog()?.textContent).toContain('Odebrat gone z dashboardu?')
    await answerDialog(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/gone', { method: 'DELETE' })
    expect(window.location.hash).toBe('#/overview')
    wrapper.unmount()
  })

  it('reports a repo the dashboard does not know', async () => {
    const fetchMock = stubApi()
    go('#/r/nope/runs')
    const wrapper = mount(App)
    await flushPromises()
    const screen = wrapper.get('[data-test="unknown-repo"]')
    expect(screen.get('h1').text()).toBe('Repo nope v dashboardu není')
    expect(screen.get('a').attributes('href')).toBe('#/overview')
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/repos/nope'))).toBe(false)
    wrapper.unmount()
  })

  it('redirects a legacy single-repo hash to the overview', async () => {
    stubApi()
    go('#/runs/r-1')
    const wrapper = mount(App)
    await flushPromises()
    expect(window.location.hash).toBe('#/overview')
    expect(wrapper.find('[data-test="readiness-warning"]').exists()).toBe(true)
    wrapper.unmount()
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import OverviewView from './OverviewView.vue'
import type { OverviewData, RepoItem } from '@/lib/api'
import { BY_PROJECT_KEY, OVERVIEW_POLL_MS } from '@/lib/overview'
import { config, factory, failed, overview, repo, review, running, tasks } from '@/test/overviewFixtures'
import { answerDialog, openDialog } from '@/test/modal'
import { defineComponent, onMounted } from 'vue'

const readyCheck = defineComponent({
  emits: ['ready'],
  setup(_, { emit }) { onMounted(() => emit('ready', true)); return () => null },
})
const global = { stubs: { OverviewReadiness: readyCheck } }

const NOW = new Date('2026-10-06T10:05:00+00:00')

function envelope(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

const REGISTERED: RepoItem[] = [
  { id: 'x', name: 'x', path: '/work/x', added_at: '', status: 'ok', factory: null },
]

const DATA = overview([
  repo('calm-b'),
  repo('calm-a', { last_activity: '2026-10-06T09:05:00+00:00' }),
  repo('busy', { running: [running()] }),
  repo('waiting', { review: [review()] }),
  repo('merging', { automerge: [review({ task_id: 'M01-S01-T09', pr_id: '9' })] }),
  repo('broken', {
    failed: [failed({ failure_kind: 'writes_violation' })],
    running: [running({ run_id: 'run-dead', process: 'ended', status_label: 'proces skončil' })],
  }),
  repo('dirty', { state: 'uncommitted', config: config({ uncommitted: [{ path: '.factory/a' }], clean: false }) }),
  repo('gone', { state: 'missing', config: null, has_trace: false, last_activity: null }),
])

let visibility: DocumentVisibilityState = 'visible'

function stubOverview(data: () => OverviewData = () => DATA) {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === '/api/overview') return envelope(data())
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function overviewCalls(fetchMock: ReturnType<typeof stubOverview>): number {
  return fetchMock.mock.calls.filter(([url]) => url === '/api/overview').length
}

function setVisibility(value: DocumentVisibilityState) {
  visibility = value
  document.dispatchEvent(new Event('visibilitychange'))
}

async function mountView() {
  const wrapper = mount(OverviewView, { props: { repos: REGISTERED }, global })
  await flushPromises()
  return wrapper
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  localStorage.removeItem(BY_PROJECT_KEY)
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  vi.setSystemTime(NOW)
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  delete (document as unknown as Record<string, unknown>).visibilityState
})

describe('OverviewView', () => {
  it('toggles busy project rows and chips through the header switch', async () => {
    stubOverview(() => overview([repo('busy', {
      projects: [
        { id: 'A', title: 'Alpha', tasks: tasks({ running: 1, ready: 2 }) },
        { id: 'B', title: 'Beta', tasks: tasks({ running: 1, ready: 3, 'in review': 1 }) },
      ],
      tasks: tasks({ running: 2, ready: 5, 'in review': 1 }),
      running: [
        running({ project: 'A', run_id: 'run-a', task_id: 'A-T01' }),
        running({ project: 'B', run_id: 'run-b', task_id: 'B-T01' }),
      ],
      review: [review({ project: 'B', task_id: 'B-T02' })],
    })]))
    const wrapper = await mountView()
    const card = wrapper.get('[data-test="overview-card"][data-repo="busy"]')
    const projectSwitch = wrapper.get('input[data-test="by-project"]')
    expect((projectSwitch.element as HTMLInputElement).checked).toBe(true)

    const assertGrouped = () => {
      const sections = card.findAll('[data-test="project-section"]')
      expect(sections).toHaveLength(2)
      expect(sections[0].findAll('[data-test="row-running"]').map((r) => r.attributes('data-run'))).toEqual(['run-a'])
      expect(sections[0].find('[data-test="row-review"]').exists()).toBe(false)
      expect(sections[0].get('[data-state="ready"] b').text()).toBe('2')
      expect(sections[1].findAll('[data-test="row-running"]').map((r) => r.attributes('data-run'))).toEqual(['run-b'])
      expect(sections[1].get('[data-test="row-review"]').attributes('data-task')).toBe('B-T02')
      expect(sections[1].get('[data-state="ready"] b').text()).toBe('3')
      expect(card.findAll('[data-test="task-summary"]')).toHaveLength(2)
    }
    assertGrouped()

    await projectSwitch.setValue(false)
    expect(card.find('[data-test="project-section"]').exists()).toBe(false)
    expect(card.findAll('[data-test="row-running"]').map((r) => r.attributes('data-run'))).toEqual(['run-a', 'run-b'])
    expect(card.get('[data-test="row-review"]').attributes('data-task')).toBe('B-T02')
    expect(card.findAll('[data-test="task-summary"]')).toHaveLength(1)
    expect(card.get('[data-state="ready"] b').text()).toBe('5')
    expect(card.get('[data-state="running"] b').text()).toBe('2')

    await projectSwitch.setValue(true)
    assertGrouped()
  })

  it('hides the project switch when no repo has multiple projects', async () => {
    stubOverview(() => overview([repo('old'), repo('single', { projects: [{ id: 'A', title: 'Alpha', tasks: tasks() }] })]))
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="by-project"]').exists()).toBe(false)
  })

  it('groups calm repos by default and remembers switching to the summary', async () => {
    stubOverview(() => overview([repo('calm', { tasks: tasks({ ready: 3 }), projects: [
      { id: 'A', title: 'Alpha', tasks: tasks({ ready: 1 }) },
      { id: 'B', title: 'Beta', tasks: tasks({ ready: 2 }) },
    ] })]))
    const wrapper = await mountView()
    expect((wrapper.get('[data-test="by-project"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.findAll('[data-test="project-section"]')).toHaveLength(2)
    await wrapper.get('input[data-test="by-project"]').setValue(false)
    expect(wrapper.find('[data-test="project-section"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="task-summary"]').text()).toContain('3')
    expect(localStorage.getItem(BY_PROJECT_KEY)).toBe('0')
    wrapper.unmount()
    const again = await mountView()
    expect((again.get('[data-test="by-project"]').element as HTMLInputElement).checked).toBe(false)
  })

  it('orders the cards by urgency and folds calm repos into one line each', async () => {
    stubOverview()
    const wrapper = await mountView()
    const cards = wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))
    expect(cards).toEqual(['dirty', 'gone', 'broken', 'waiting', 'busy', 'merging'])
    const calm = wrapper.findAll('[data-test="calm-repo"]')
    expect(calm.map((c) => c.attributes('data-repo'))).toEqual(['calm-a', 'calm-b'])
    expect(calm[0].text()).toContain('v klidu')
    expect(calm[0].get('[data-test="last-activity"]').text()).toContain('před 1 h')
    expect(calm[0].find('[data-test="row-running"]').exists()).toBe(false)
  })

  it('offers Spustit továrnu in the calm list and the task summary on a card', async () => {
    const fetchMock = stubOverview(() =>
      overview([
        repo('calm-ready', { factory: factory({ can_start: true, ready: 2 }), tasks: tasks({ ready: 2 }) }),
        repo('busy', { running: [running()], tasks: tasks({ running: 1, done: 3 }), factory: factory({ running: 1 }) }),
      ]),
    )
    const wrapper = await mountView()
    const calm = wrapper.get('[data-test="calm-repo"]')
    expect(calm.attributes('data-repo')).toBe('calm-ready')
    expect(calm.find('[data-test="factory-start"]').exists()).toBe(true)
    const card = wrapper.get('[data-test="overview-card"]')
    expect(card.get('[data-test="task-summary"]').text()).toBe('Běží 1Hotovo 3')
    expect(card.find('[data-test="factory-stop"]').exists()).toBe(true)
    expect(card.find('[data-test="factory-start"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.every(([, init]) => !init || init.method !== 'POST')).toBe(true)
  })

  it('shows the totals and filters the cards by a click on one', async () => {
    stubOverview()
    const wrapper = await mountView()
    const count = (id: string) => wrapper.get(`[data-test="total-${id}"] [data-test="total-count"]`).text()
    expect([count('running'), count('review'), count('automerge'), count('failed'), count('problems')]).toEqual([
      '1',
      '1',
      '1',
      '2',
      '2',
    ])
    expect(wrapper.get('[data-test="total-failed"]').text()).toContain('Selhalo')
    expect(wrapper.get('[data-test="total-review"]').text()).toContain('Čeká na review')
    expect(wrapper.get('[data-test="total-automerge"]').text()).toContain('Čeká na automerge PR')

    await wrapper.get('[data-test="total-review"]').trigger('click')
    expect(wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))).toEqual(['waiting'])
    await wrapper.get('[data-test="total-automerge"]').trigger('click')
    expect(wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))).toEqual(['merging'])

    await wrapper.get('[data-test="total-failed"]').trigger('click')
    expect(wrapper.get('[data-test="total-failed"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))).toEqual(['broken'])
    expect(wrapper.find('[data-test="calm-repo"]').exists()).toBe(false)

    await wrapper.get('[data-test="total-problems"]').trigger('click')
    expect(wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))).toEqual(['dirty', 'gone'])

    await wrapper.get('[data-test="total-problems"]').trigger('click')
    expect(wrapper.findAll('[data-test="overview-card"]')).toHaveLength(6)
    expect(wrapper.findAll('[data-test="calm-repo"]')).toHaveLength(2)
  })

  it('links every row: run, review, failed run and config commit', async () => {
    stubOverview()
    const wrapper = await mountView()
    const busy = wrapper.get('[data-repo="busy"]')
    const run = busy.get('[data-test="row-running"]')
    expect(run.element.tagName).toBe('A')
    expect(run.attributes('href')).toBe('#/r/busy/runs/run-1')
    expect(run.text()).toContain('M01-S01-T01')
    expect(run.text()).toContain('Schema')
    expect(run.text()).toContain('build-test-review')
    expect(run.get('[data-test="row-phase"]').text()).toBe('build · pokus 2')
    expect(run.get('[data-test="row-elapsed"]').text()).toBe('5m 00s')
    expect(run.get('[data-test="row-cost"]').text()).toBe('$1.25')

    const pr = wrapper.get('[data-repo="waiting"] [data-test="row-review"]')
    expect(pr.attributes('href')).toBe('#/r/waiting/review/M01-S01-T02')
    expect(pr.text()).toContain('PR #42')
    expect(pr.get('[data-test="row-age"]').text()).toBe('před 1 h')
    expect(pr.text()).toContain('podle trace')

    const fails = wrapper.get('[data-repo="broken"]').findAll('[data-test="row-failed"]')
    expect(fails.map((f) => f.attributes('href'))).toEqual(['#/r/broken/runs/run-dead', '#/r/broken/runs/run-f'])
    expect(fails[0].get('[data-test="row-error"]').text()).toBe('proces skončil')
    // the failure kind, not the start of the error text
    expect(fails[1].get('[data-test="row-error"]').text()).toBe('Zápis mimo writes')

    const cfg = wrapper.get('[data-repo="dirty"] [data-test="row-config"]')
    expect(cfg.attributes('href')).toBe('#/r/dirty/factory/config_commit')
    expect(cfg.text()).toBe('Necommitnutá konfigurace')

    expect(wrapper.get('[data-repo="busy"] [data-test="last-activity"]').text()).toContain('před 5 min')
  })

  it('counts the elapsed time of a run in the browser', async () => {
    stubOverview()
    const wrapper = await mountView()
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(wrapper.get('[data-repo="busy"] [data-test="row-elapsed"]').text()).toBe('5m 01s')
  })

  it('shows a missing folder', async () => {
    stubOverview()
    const wrapper = await mountView()
    const gone = wrapper.get('[data-repo="gone"]')
    expect(gone.get('[data-test="state-missing"]').text()).toBe('Složka nenalezena')
  })

  it('reloads every 2 s, on focus and by the refresh button, only reading', async () => {
    const fetchMock = stubOverview()
    const wrapper = await mountView()
    expect(overviewCalls(fetchMock)).toBe(1)
    vi.advanceTimersByTime(OVERVIEW_POLL_MS)
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(2)
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(3)
    await wrapper.get('[data-test="overview-refresh"]').trigger('click')
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(4)
    expect(fetchMock.mock.calls.every(([, init]) => init === undefined)).toBe(true)
  })

  it('pauses the reload in a hidden tab and reloads on return', async () => {
    const fetchMock = stubOverview()
    await mountView()
    setVisibility('hidden')
    vi.advanceTimersByTime(OVERVIEW_POLL_MS * 5)
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(1)
    setVisibility('visible')
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(2)
    vi.advanceTimersByTime(OVERVIEW_POLL_MS)
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(3)
  })

  it('stops reloading when it leaves the page', async () => {
    const fetchMock = stubOverview()
    const wrapper = await mountView()
    wrapper.unmount()
    vi.advanceTimersByTime(OVERVIEW_POLL_MS * 3)
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(overviewCalls(fetchMock)).toBe(1)
  })

  it('shows the newest data after a reload', async () => {
    let data = overview([repo('a')])
    stubOverview(() => data)
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="overview-card"]').exists()).toBe(false)
    data = overview([repo('a', { running: [running()] })])
    vi.advanceTimersByTime(OVERVIEW_POLL_MS)
    await flushPromises()
    expect(wrapper.get('[data-test="overview-card"]').attributes('data-repo')).toBe('a')
  })

  function stubRemoval(deletion?: Response) {
    let removed = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/repos/gone' && init?.method === 'DELETE') {
        if (deletion) return deletion
        removed = true
        return envelope({ removed: { id: 'gone' }, uninstall: null })
      }
      if (url === '/api/overview') return envelope(removed ? overview([repo('busy', { running: [running()] })]) : DATA)
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  async function openRemoval() {
    const wrapper = mount(OverviewView, { props: { repos: REGISTERED }, attachTo: document.body, global })
    await flushPromises()
    await wrapper.get('[data-test="overview-card"][data-repo="gone"] [data-test="repo-menu"]').trigger('click')
    await wrapper.get('[data-test="overview-card"][data-repo="gone"] [data-test="card-remove"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  function deleteBody(fetchMock: ReturnType<typeof stubRemoval>): unknown {
    const call = fetchMock.mock.calls.find(([url, init]) => url === '/api/repos/gone' && init?.method === 'DELETE')
    return call ? JSON.parse(String(call[1]?.body)) : undefined
  }

  it('removes a repo only from the dashboard, leaving its folder and .factory/ alone', async () => {
    const fetchMock = stubRemoval()
    const wrapper = mount(OverviewView, { props: { repos: REGISTERED }, attachTo: document.body, global })
    await flushPromises()
    expect(wrapper.findAll('[data-test="card-remove"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-test="overview-card"] [data-test="repo-menu"]')).toHaveLength(6)
    expect(wrapper.findAll('[data-test="calm-repo"] [data-test="repo-menu"]')).toHaveLength(2)
    await wrapper.get('[data-test="calm-repo"] [data-test="repo-menu"]').trigger('click')
    expect(wrapper.findAll('[data-test="calm-remove"]')).toHaveLength(1)
    await wrapper.get('[data-test="calm-repo"] [data-test="repo-menu"]').trigger('click')
    expect(wrapper.findAll('[data-test="calm-remove"]')).toHaveLength(0)
    await wrapper.get('[data-test="overview-card"][data-repo="gone"] [data-test="repo-menu"]').trigger('click')
    await wrapper.get('[data-test="overview-card"][data-repo="gone"] [data-test="card-remove"]').trigger('click')
    await flushPromises()
    const dialog = openDialog()!
    expect(dialog.textContent).toContain('Odebrat repozitář gone?')
    expect(dialog.textContent).toContain('Repo se odpojí jen z dashboardu')
    expect(dialog.textContent).toContain('.factory/, backlog, specifikace i dokumentace v repu zůstanou')
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/removal'))).toBe(false)
    await answerDialog(true)
    expect(deleteBody(fetchMock)).toEqual({ uninstall: false })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[data-test="overview-card"][data-repo="gone"]').exists()).toBe(false)
  })

  it('offers adding a repo under the repo list', async () => {
    stubRemoval()
    const wrapper = mount(OverviewView, { props: { repos: REGISTERED }, attachTo: document.body, global })
    await flushPromises()
    const link = wrapper.get('[data-test="overview-add-repo"]')
    expect(link.text()).toBe('Přidat repozitář')
    expect(link.attributes('href')).toBe('#/repos/add')
  })

  it('keeps the repo when the removal is cancelled', async () => {
    const fetchMock = stubRemoval()
    await openRemoval()
    await answerDialog(false)
    expect(deleteBody(fetchMock)).toBeUndefined()
  })

  it('reports a failed removal', async () => {
    stubRemoval(new Response(JSON.stringify({ ok: false, data: null, error: { code: 'registry_error', message: 'registry locked', path: null, id: null, issues: [] }, warnings: [] }), { status: 409 }))
    const wrapper = await openRemoval()
    await answerDialog(true)
    expect(wrapper.get('[data-test="remove-error"]').text()).toContain('registry locked')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('offers adding a repo when none is registered', async () => {
    stubOverview()
    const wrapper = mount(OverviewView, { props: { repos: [] }, global })
    await flushPromises()
    expect(wrapper.get('[data-test="add-repo-link"]').attributes('href')).toBe('#/repos/add')
    expect(wrapper.get('[data-test="no-repos"] [data-test="try-demo"]').text()).toBe('Vyzkoušet na ukázce')
  })

  it('has no sample button once a repo is registered', async () => {
    stubOverview()
    const wrapper = mount(OverviewView, { props: { repos: REGISTERED }, global })
    await flushPromises()
    expect(wrapper.find('[data-test="try-demo"]').exists()).toBe(false)
  })
})

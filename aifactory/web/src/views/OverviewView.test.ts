import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import OverviewView from './OverviewView.vue'
import type { OverviewData, RepoItem } from '@/lib/api'
import { OVERVIEW_POLL_MS } from '@/lib/overview'
import { config, failed, overview, repo, review, running } from '@/test/overviewFixtures'
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
  repo('broken', {
    failed: [failed()],
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
  it('orders the cards by urgency and folds calm repos into one line each', async () => {
    stubOverview()
    const wrapper = await mountView()
    const cards = wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))
    expect(cards).toEqual(['dirty', 'gone', 'broken', 'waiting', 'busy'])
    const calm = wrapper.findAll('[data-test="calm-repo"]')
    expect(calm.map((c) => c.attributes('data-repo'))).toEqual(['calm-a', 'calm-b'])
    expect(calm[0].text()).toContain('v klidu')
    expect(calm[0].get('[data-test="last-activity"]').text()).toContain('před 1 h')
    expect(calm[0].find('[data-test="row-running"]').exists()).toBe(false)
  })

  it('shows the totals and filters the cards by a click on one', async () => {
    stubOverview()
    const wrapper = await mountView()
    const count = (id: string) => wrapper.get(`[data-test="total-${id}"] [data-test="total-count"]`).text()
    expect([count('running'), count('review'), count('failed'), count('problems')]).toEqual(['1', '1', '2', '2'])
    expect(wrapper.get('[data-test="total-failed"]').text()).toContain('Selhalo')

    await wrapper.get('[data-test="total-failed"]').trigger('click')
    expect(wrapper.get('[data-test="total-failed"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))).toEqual(['broken'])
    expect(wrapper.find('[data-test="calm-repo"]').exists()).toBe(false)

    await wrapper.get('[data-test="total-problems"]').trigger('click')
    expect(wrapper.findAll('[data-test="overview-card"]').map((c) => c.attributes('data-repo'))).toEqual(['dirty', 'gone'])

    await wrapper.get('[data-test="total-problems"]').trigger('click')
    expect(wrapper.findAll('[data-test="overview-card"]')).toHaveLength(5)
    expect(wrapper.findAll('[data-test="calm-repo"]')).toHaveLength(2)
  })

  it('links every row: run, review, failed run and settings', async () => {
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
    expect(fails[1].get('[data-test="row-error"]').text()).toBe('tests failed')

    const cfg = wrapper.get('[data-repo="dirty"] [data-test="row-config"]')
    expect(cfg.attributes('href')).toBe('#/r/dirty/settings')
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

  const PLAN = {
    repo: '/w/gone', base: 'main', base_sha: 'abc', target: 'base', digest: 'd',
    files: [{ path: '.factory/config.yaml', action: 'delete' }, { path: '.gitignore', action: 'modify' }],
    blockers: [] as { code: string; message: string; fix?: string }[],
    own_items: [{ type: 'agent', name: 'mine', state: 'local' }, { type: 'workflow', name: 'flow', state: 'modified' }],
  }

  function stubRemoval(plan: unknown, deletion?: Response) {
    let removed = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/repos/gone/removal') {
        return plan instanceof Response ? plan : envelope(plan)
      }
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
    await wrapper.get('[data-test="overview-card"][data-repo="gone"] [data-test="card-remove"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  function deleteBody(fetchMock: ReturnType<typeof stubRemoval>): unknown {
    const call = fetchMock.mock.calls.find(([url, init]) => url === '/api/repos/gone' && init?.method === 'DELETE')
    return call ? JSON.parse(String(call[1]?.body)) : undefined
  }

  it('removes a repo after showing its removal plan and exports the checked own items', async () => {
    const fetchMock = stubRemoval(PLAN)
    const wrapper = mount(OverviewView, { props: { repos: REGISTERED }, attachTo: document.body, global })
    await flushPromises()
    expect(wrapper.findAll('[data-test="card-remove"]')).toHaveLength(5)
    expect(wrapper.findAll('[data-test="calm-remove"]')).toHaveLength(2)
    await wrapper.get('[data-test="overview-card"][data-repo="gone"] [data-test="card-remove"]').trigger('click')
    await flushPromises()
    const dialog = openDialog()!
    expect(dialog.textContent).toContain('Odebrat repozitář gone?')
    expect(dialog.textContent).toContain('.factory/ a řádky factory v .gitignore, commitne to do main')
    expect(dialog.textContent).toContain('Backlog, specifikace a dokumentace v repu zůstanou.')
    expect(dialog.textContent).toContain('Commit změní 2 soubory.')
    const boxes = dialog.querySelectorAll<HTMLInputElement>('[data-test="removal-export"]')
    expect([...boxes].map((b) => b.checked)).toEqual([true, true])
    expect(dialog.querySelectorAll('[data-test="removal-own-item"]')[0].textContent).toContain('Přesunout do knihovny')
    boxes[1].click()
    await flushPromises()
    await answerDialog(true)
    expect(deleteBody(fetchMock)).toEqual({ export: [{ type: 'agent', name: 'mine' }] })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[data-test="overview-card"][data-repo="gone"]').exists()).toBe(false)
  })

  it('lists blockers and keeps Odebrat disabled while any exists', async () => {
    const fetchMock = stubRemoval({ ...PLAN, own_items: [], blockers: [{ code: 'dirty_paths', message: 'Necommitnuté změny v .factory/.', fix: 'Commitni je.' }] })
    await openRemoval()
    const dialog = openDialog()!
    expect(dialog.querySelector('[data-test="removal-blocker"]')?.textContent).toContain('Necommitnuté změny v .factory/. Commitni je.')
    expect(dialog.querySelector<HTMLButtonElement>('[data-test="confirm-ok"]')?.disabled).toBe(true)
    expect(dialog.querySelector('[data-test="removal-own-items"]')).toBeNull()
    await answerDialog(false)
    expect(deleteBody(fetchMock)).toBeUndefined()
  })

  it('removes only the registry entry when the removal plan cannot be read', async () => {
    const fetchMock = stubRemoval(new Response(JSON.stringify({ ok: false, data: null, error: { code: 'not_git', message: 'folder is gone', path: null, id: null, issues: [] }, warnings: [] }), { status: 400 }))
    await openRemoval()
    expect(openDialog()?.textContent).toContain('Plán odebrání se nepodařilo načíst: folder is gone')
    await answerDialog(true)
    expect(deleteBody(fetchMock)).toEqual({ uninstall: false })
  })

  it('reports a failed removal', async () => {
    stubRemoval(PLAN, new Response(JSON.stringify({ ok: false, data: null, error: { code: 'push_failed', message: 'push refused', path: null, id: null, issues: [] }, warnings: [] }), { status: 409 }))
    const wrapper = await openRemoval()
    await answerDialog(true)
    expect(wrapper.get('[data-test="remove-error"]').text()).toContain('push refused')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('offers adding a repo when none is registered', async () => {
    stubOverview()
    const wrapper = mount(OverviewView, { props: { repos: [] }, global })
    await flushPromises()
    expect(wrapper.get('[data-test="add-repo-link"]').attributes('href')).toBe('#/repos/add')
  })
})

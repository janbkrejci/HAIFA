import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import OverviewView from './OverviewView.vue'
import ProblemsView from './ProblemsView.vue'
import DemoBanner from '@/components/demo/DemoBanner.vue'
import DemoSteps from '@/components/demo/DemoSteps.vue'
import { setLocale } from '@/lib/i18n'
import { lastStart } from '@/lib/demo'
import { autoActionText, dashboardError } from '@/lib/dashboardMessages'
import { ApiError } from '@/lib/api'
import { backlogText, failedRows, TOTALS } from '@/lib/overview'
import { factory, overview, repo, running, tasks } from '@/test/overviewFixtures'
import { openDialog } from '@/test/modal'
import type { RunSummary } from '@/lib/runs'

const registered = [{ id: 'alpha', name: 'Moje české repo', path: '/work/české', added_at: '', status: 'ok' as const, factory: null }]
const active = repo('alpha', {
  name: registered[0]!.name, running: [running({ task_title: 'Uživatelské zadání', project: 'P' })],
  tasks: tasks({ running: 1 }), projects: [{ id: 'P', title: 'Můj projekt', tasks: tasks({ running: 1 }) }],
  factory: factory({ can_start: true, ready: 1 }),
})
function envelope(data: unknown) { return new Response(JSON.stringify({ ok: true, data, warnings: [], error: null })) }
function requests() {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/overview') return envelope(overview([active, repo('calm', { last_activity: null })]))
    if (url.endsWith('/control/start')) return envelope({ started: [{ task_id: 'T', run_id: 'r' }], skipped: [] })
    if (url.startsWith('/api/machine/check')) return envelope({ ok: false, checked: true, checked_at: 'now', findings: [{ code: 'git_missing', severity: 'error', scope: 'machine', message: 'git is not on PATH', fix: 'install git', action: null }], harness_repos: {} })
    if (url === '/api/repos') return envelope({ repos: registered })
    if (url === '/api/library?items=0') return envelope({ exists: true })
    if (url.endsWith('/factory/roster?summary=1')) return envelope({ agents: 1 })
    if (url.endsWith('/backlog/summary')) return envelope({ projects: 1 })
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
enableAutoUnmount(afterEach)
beforeEach(() => { localStorage.clear(); setLocale('en') })
afterEach(() => { vi.unstubAllGlobals(); setLocale('en'); lastStart.value = null; document.body.innerHTML = '' })

describe('overview locale without remounting', () => {
  it('preserves filters, project options, identity, requests and user content in EN → CS → EN', async () => {
    const fetchMock = requests()
    const wrapper = mount(OverviewView, { props: { repos: registered } })
    await flushPromises()
    expect(wrapper.get('[data-test="calm-repo"]').text()).toContain('no activity')
    await wrapper.get('[data-test="show-finished"]').setValue(true)
    await wrapper.get('[data-test="total-running"]').trigger('click')
    const card = wrapper.get('[data-test="overview-card"]').element
    const calls = fetchMock.mock.calls.length
    for (const [language, heading, label] of [['cs', 'Přehled', 'Běží'], ['en', 'Overview', 'Running']] as const) {
      setLocale(language)
      await nextTick()
      expect(wrapper.get('h1').text()).toBe(heading)
      expect(wrapper.get('[data-test="total-running"]').text()).toContain(label)
      expect(wrapper.get('[data-test="total-running"]').attributes('aria-pressed')).toBe('true')
      expect(wrapper.get('[data-test="overview-card"]').element).toBe(card)
      expect((wrapper.get('[data-test="show-finished"]').element as HTMLInputElement).checked).toBe(true)
      expect(wrapper.find('[data-test="calm-repo"]').exists()).toBe(false)
      expect(wrapper.text()).toContain('Uživatelské zadání')
      expect(wrapper.text()).toContain('Můj projekt')
      expect(wrapper.text()).toContain(registered[0]!.name)
      expect(fetchMock.mock.calls).toHaveLength(calls)
    }
  })

  it('retranslates completed feedback and an open stop confirmation', async () => {
    requests()
    const wrapper = mount(OverviewView, { props: { repos: registered }, attachTo: document.body })
    await flushPromises()
    await wrapper.get('[data-test="factory-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="factory-start-message"]').text()).toBe('Started 1 run')
    await wrapper.get('[data-test="factory-stop"]').trigger('click')
    await nextTick()
    const dialog = openDialog()
    if (!dialog) throw new Error('confirm dialog is not open')
    expect(dialog.textContent).toContain('Stop all runs')
    setLocale('cs')
    await nextTick()
    expect(wrapper.get('[data-test="factory-start-message"]').text()).toBe('Spuštěno 1 běh')
    expect(openDialog()).toBe(dialog)
    expect(dialog.textContent).toContain('Zastavit všechny běhy')
    expect(dialog.textContent).toContain('Zastaví se 1 běh')
  })

  it('translates loaded findings from codes while preserving original diagnostics', async () => {
    const fetchMock = requests()
    const wrapper = mount(ProblemsView)
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Problems and solutions')
    expect(wrapper.text()).toContain('Git unavailable')
    expect(wrapper.get('details').text()).toContain('git is not on PATH')
    const calls = fetchMock.mock.calls.length
    setLocale('cs')
    await nextTick()
    expect(wrapper.get('h1').text()).toBe('Problémy a řešení')
    expect(wrapper.text()).toContain('Git není dostupný')
    expect(wrapper.get('summary').text()).toBe('Technické podrobnosti')
    expect(fetchMock.mock.calls).toHaveLength(calls)
  })

  it('retranslates an API failure already displayed without retrying the request', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      ok: false, data: null, warnings: [], error: { code: 'trace_db_locked', message: 'database is locked', issues: [] },
    }), { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(OverviewView, { props: { repos: registered } })
    await flushPromises()
    expect(wrapper.get('[data-test="overview-error"]').text()).toContain('The run database is busy.')
    setLocale('cs')
    await nextTick()
    expect(wrapper.get('[data-test="overview-error"]').text()).toContain('Databáze běhů je obsazená.')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([1, 2, 5])('uses catalog plurals and a stable process state for %s files', count => {
    const data = repo('r', { backlog: { state: 'dirty', count, error: null }, running: [running({ process: 'ended', status_label: 'proces skončil' })] })
    expect(backlogText(data)).toBe(`Uncommitted backlog: ${count} ${count === 1 ? 'file' : 'files'}`)
    expect(failedRows(data)[0]?.label).toBe('process ended')
    setLocale('cs')
    expect(backlogText(data)).toBe(`Necommitnutý backlog: ${count} ${count === 1 ? 'soubor' : count < 5 ? 'soubory' : 'souborů'}`)
    expect(failedRows(data)[0]?.label).toBe('proces skončil')
    expect(TOTALS[0]?.label).toBe('Běží')
  })

  it('uses action fields and request codes without interpreting saved sentences', () => {
    const action = { action: 'fallback', at: '', task_id: 'T', run_id: 'r', failure_kind: 'quota', ok: true, text: 'Uložená česká věta', detail: { from: { harness: 'codex' }, to: { harness: 'claude' } } }
    const error = new ApiError('run_in_progress', 'Uložená česká věta')
    expect(autoActionText(action)).toContain('GIRO continued with Claude Code')
    expect(dashboardError(error)).toBe('A run is in progress in the repository.')
    setLocale('cs')
    expect(autoActionText(action)).toBe('GIRO pokračovala na Claude Code po vyčerpání kvóty Codexu')
    expect(dashboardError(error)).toBe('V repozitáři právě probíhá běh.')
    expect(action.text).toBe('Uložená česká věta')
    expect(error.message).toBe('Uložená česká věta')
  })

  it('keeps the demo run and live step while translating explanations', async () => {
    lastStart.value = { repoId: 'sample', runId: 'demo-run', harness: { harness: 'codex', model: 'model' }, error: null }
    const banner = mount(DemoBanner, { props: { repoId: 'sample', path: '/work/ukázka' } })
    const steps = mount(DemoSteps, { props: { run: { state: 'running', pr: null, task_id: 'DEMO-S01-T01' } as RunSummary, phases: [] } })
    expect(banner.text()).toContain('Demo repository.')
    expect(steps.text()).toContain('What is happening now')
    const link = banner.get('[data-test="demo-run-link"]').attributes('href')
    const current = steps.get('[data-state="current"]').attributes('data-step')
    setLocale('cs')
    await nextTick()
    expect(banner.text()).toContain('Ukázkové repo.')
    expect(steps.text()).toContain('Co se právě děje')
    expect(banner.get('[data-test="demo-run-link"]').attributes('href')).toBe(link)
    expect(steps.get('[data-state="current"]').attributes('data-step')).toBe(current)
    expect(lastStart.value?.runId).toBe('demo-run')
  })
})

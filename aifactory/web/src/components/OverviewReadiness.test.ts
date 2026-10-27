import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import OverviewView from '@/views/OverviewView.vue'
import OverviewReadiness from './OverviewReadiness.vue'
import type { MachineCheck, RepoItem } from '@/lib/api'
import { overview, repo } from '@/test/overviewFixtures'
import { answerDialog } from '@/test/modal'

const registered: RepoItem = { id: 'a', name: 'A', path: '/w/a', added_at: '', status: 'ok', factory: null }
const machine: MachineCheck = { ok: true, findings: [], checked_at: 'now', cached: false, harness_repos: { codex: 1 } }

function envelope(data: unknown) { return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] })) }
function stub(options: { machine?: MachineCheck; repos?: RepoItem[]; fail?: boolean; pending?: Promise<Response> } = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/repos/missing' && init?.method === 'DELETE') return envelope({ removed: { id: 'missing' } })
    if (url.startsWith('/api/machine/check')) {
      if (options.fail) throw new Error('Server není dostupný')
      if (options.pending) return options.pending
      return envelope(options.machine ?? machine)
    }
    if (url === '/api/library?items=0') return envelope({ exists: true })
    if (url === '/api/repos') return envelope({ repos: options.repos ?? [registered] })
    if (url === '/api/repos/a/factory/roster') return envelope({ agents: [{ name: 'builder' }], workflow_tasks: {} })
    if (url === '/api/repos/a/backlog') return envelope({ items: [{ id: 'M01' }] })
    if (url === '/api/overview') return envelope(overview([repo('a')]))
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

enableAutoUnmount(afterEach)
beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('overview readiness', () => {
  it('keeps a green chip visible and runs a fresh check when clicked', async () => {
    const options: { pending?: Promise<Response> } = {}
    const fetchMock = stub(options)
    const wrapper = mount(OverviewReadiness, { props: { chip: true } })
    expect(wrapper.find('.status-icon-chip').exists()).toBe(false)
    await flushPromises()
    expect(wrapper.get('[data-test="readiness-success"]').text()).toBe('')
    expect(wrapper.get('[data-test="readiness-success"]').attributes('aria-label')).toBe('Systém v pořádku – kliknutím spustíš kontrolu znovu')
    await wrapper.get('[data-test="readiness-success"]').trigger('focusin')
    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toBe(wrapper.get('[data-test="readiness-success"]').attributes('aria-label'))
    await wrapper.get('[data-test="readiness-success"]').trigger('focusout')
    await vi.advanceTimersByTimeAsync(10000)
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
    const before = fetchMock.mock.calls.length
    let finish!: (response: Response) => void
    options.pending = new Promise(resolve => { finish = resolve })
    await wrapper.get('[data-test="readiness-success"]').trigger('click')
    expect(wrapper.get('[data-test="readiness-checking"]').attributes('aria-label')).toBe('Probíhá kontrola')
    finish(envelope(machine))
    await flushPromises()
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before)
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1')
    const overviewWrapper = mount(OverviewView, { props: { repos: [registered] } })
    await flushPromises()
    expect(overviewWrapper.get('[data-test="repo-page"]').text()).toContain('Přehled')
    expect(overviewWrapper.find('[data-test="readiness-success"]').exists()).toBe(false)
  })

  describe.each([true, false])('manual check during a silent refresh (chip=%s)', chip => {
    it.each(['before', 'after', 'failure'] as const)('ignores an older response completing %s the manual check', async order => {
      const options: { pending?: Promise<Response> } = {}
      const fetchMock = stub(options)
      const wrapper = mount(OverviewReadiness, { props: { chip } })
      await flushPromises()
      let finishSilent!: (response: Response) => void
      let failSilent!: (error: Error) => void
      options.pending = new Promise((resolve, reject) => { finishSilent = resolve; failSilent = reject })
      window.dispatchEvent(new Event('factory-applied'))
      await flushPromises()
      expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
      let finishManual!: (response: Response) => void
      options.pending = new Promise(resolve => { finishManual = resolve })
      await wrapper.get(chip ? '[data-test="readiness-success"]' : '[data-test="readiness-retry"]').trigger('click')
      expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1')
      expect(wrapper.get('[data-test="readiness-checking"]').text()).toBe(chip ? '' : 'Probíhá kontrola')
      if (order === 'before') {
        finishSilent(envelope(machine))
        await flushPromises()
        expect(wrapper.find('[data-test="readiness-checking"]').exists()).toBe(true)
        const before = fetchMock.mock.calls.length
        window.dispatchEvent(new Event('factory-applied'))
        await flushPromises()
        expect(fetchMock.mock.calls.length).toBe(before)
      }
      finishManual(envelope({ ...machine, findings: [{ code: 'tool_missing', severity: 'error', scope: 'machine', message: 'Chybí Git.', fix: 'Nainstaluj Git.', action: null }] }))
      await flushPromises()
      expect(wrapper.find('[data-test="readiness-warning"]').exists()).toBe(true)
      const result = wrapper.text()
      if (order === 'after') finishSilent(envelope(machine))
      if (order === 'failure') failSilent(new Error('Stará odpověď selhala'))
      await flushPromises()
      expect(wrapper.text()).toBe(result)
      if (!chip) expect(result).toContain('Chybí Git.')
    })
  })

  it.each([true, false])('labels a slow initial read as loading, not a new check (chip=%s)', async chip => {
    let finish!: (response: Response) => void
    stub({ pending: new Promise(resolve => { finish = resolve }) })
    const wrapper = mount(OverviewReadiness, { props: { chip } })
    await vi.advanceTimersByTimeAsync(999)
    expect(wrapper.find('[data-test="readiness-checking"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(wrapper.get('[data-test="readiness-loading"]').text()).toBe(chip ? '' : 'Načítání stavu')
    if (chip) expect(wrapper.get('[data-test="readiness-loading"]').attributes('aria-label')).toBe('Načítání stavu')
    expect(wrapper.find('[data-test="readiness-checking"]').exists()).toBe(false)
    finish(envelope(machine))
    await flushPromises()
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
  })

  it.each([true, false])('silently reads cached results after factory-applied and preserves issues (chip=%s)', async chip => {
    const options: { machine: MachineCheck; pending?: Promise<Response> } = {
      machine: { ...machine, findings: [{ code: 'tool_missing', severity: 'error', scope: 'machine', message: 'Chybí Git.', fix: 'Nainstaluj Git.', action: null }] },
    }
    const fetchMock = stub(options)
    const wrapper = mount(OverviewReadiness, { props: { chip } })
    await flushPromises()
    const previous = wrapper.text()
    let finish!: (response: Response) => void
    options.pending = new Promise(resolve => { finish = resolve })
    window.dispatchEvent(new Event('factory-applied'))
    await vi.advanceTimersByTimeAsync(1500)
    expect(wrapper.text()).toBe(previous)
    expect(wrapper.find('[data-test="readiness-checking"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/machine/check')).toHaveLength(2)
    expect(fetchMock).not.toHaveBeenCalledWith('/api/machine/check?fresh=1')
    finish(envelope(machine))
    await flushPromises()
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
  })

  it('reads the cached result once on load and does not check again on focus', async () => {
    const fetchMock = stub()
    mount(OverviewReadiness, { props: { chip: true } })
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check')
    const before = fetchMock.mock.calls.length
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(fetchMock.mock.calls.length).toBe(before)
  })

  it('links the warning chip to problems and provides concrete fixes on that page', async () => {
    const options: { machine: MachineCheck; pending?: Promise<Response> } = { machine: { ...machine, ok: false, findings: [{ code: 'tool_missing', severity: 'error', scope: 'machine', message: 'Chybí Git.', fix: 'Nainstaluj Git.', action: null }] } }
    const fetchMock = stub(options)
    const chip = mount(OverviewReadiness, { props: { chip: true } })
    const detail = mount(OverviewReadiness)
    expect(chip.find('.status-icon-chip').exists()).toBe(false)
    await flushPromises()
    expect(chip.get('[data-test="readiness-warning"]').text()).toBe('')
    expect(chip.get('[data-test="readiness-warning"]').attributes('aria-label')).toBe('Nalezeny problémy – kliknutím otevřeš seznam problémů')
    expect(chip.get('[data-test="readiness-warning"]').attributes('href')).toBe('#/problems')
    expect(detail.get('[data-test="readiness-warning"] strong').text()).toBe('Chybí Git.')
    expect(detail.get('[data-test="readiness-warning"] li span').text()).toBe('Nainstaluj Git.')
    expect(detail.get('[data-test="readiness-warning"] a').attributes('href')).toBe('#/setup')
    options.machine = machine
    let finish!: (response: Response) => void
    options.pending = new Promise(resolve => { finish = resolve })
    await detail.get('[data-test="readiness-retry"]').trigger('click')
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1')
    expect(detail.get('[data-test="readiness-checking"]').text()).toBe('Probíhá kontrola')
    finish(envelope(machine))
    await flushPromises()
    expect(detail.find('[data-test="readiness-success"]').exists()).toBe(true)
  })

  it('silently refreshes cached results after removing an unavailable repo', async () => {
    const options: { repos: RepoItem[]; pending?: Promise<Response> } = {
      repos: [registered, { ...registered, id: 'missing', name: 'Missing', status: 'missing' }],
    }
    const fetchMock = stub(options)
    const wrapper = mount(OverviewReadiness, { attachTo: document.body })
    await flushPromises()
    let finish!: (response: Response) => void
    options.pending = new Promise(resolve => { finish = resolve })
    options.repos = [registered]
    await wrapper.get('[data-test="readiness-warning"] li button').trigger('click')
    await answerDialog(true)
    await vi.advanceTimersByTimeAsync(1500)
    expect(wrapper.find('[data-test="readiness-checking"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="readiness-warning"]').text()).toContain('Missing: chybí')
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/machine/check')).toHaveLength(2)
    expect(fetchMock).not.toHaveBeenCalledWith('/api/machine/check?fresh=1')
    finish(envelope(machine))
    await flushPromises()
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
  })

  it('offers the configuration commit action when a repository has uncommitted configuration', async () => {
    stub({ repos: [{ ...registered, status: 'uncommitted' }] })
    const wrapper = mount(OverviewReadiness)
    await flushPromises()
    const warning = wrapper.get('[data-test="readiness-warning"]')
    expect(warning.text()).toContain('A: neuložená konfigurace')
    expect(warning.get('a').attributes('href')).toBe('#/r/a/factory/config_commit')
    expect(warning.text()).not.toContain('První projekt')
  })

  it('offers the sample next to adding a repository when there is none', async () => {
    stub({ repos: [] })
    const wrapper = mount(OverviewReadiness)
    await flushPromises()
    const item = wrapper.findAll('[data-test="readiness-warning"] li').find((li) => li.text().includes('Repozitář'))
    expect(item?.get('a').attributes('href')).toBe('#/repos/add')
    expect(item?.get('[data-test="try-demo"]').text()).toBe('Vyzkoušet na ukázce')
    expect(wrapper.findAll('[data-test="try-demo"]')).toHaveLength(1)
  })

  it('offers a retry after a failed request', async () => {
    const options = { fail: true }
    stub(options)
    const wrapper = mount(OverviewReadiness)
    await flushPromises()
    expect(wrapper.get('[data-test="readiness-warning"]').text()).toContain('Server není dostupný')
    options.fail = false
    await wrapper.get('[data-test="readiness-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
  })
})

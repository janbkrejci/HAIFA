import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { applyBasePull, applyFactoryPlan, fetchBasePullPlan, fetchFactoryPlan, fetchOverview } from '@/lib/api'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, traceEvent } from '@/test/fakeEventSource'
import { installPlan } from '@/test/factoryFixtures'
import { openDialog } from '@/test/modal'
import { operation, overview, repo, running } from '@/test/overviewFixtures'
import FactoryOperation from './FactoryOperation.vue'

vi.mock('@/lib/api', async original => ({ ...await original<typeof import('@/lib/api')>(), fetchFactoryPlan: vi.fn(), fetchBasePullPlan: vi.fn(), fetchOverview: vi.fn(), applyFactoryPlan: vi.fn(), applyBasePull: vi.fn() }))
enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.mocked(fetchFactoryPlan).mockResolvedValue(installPlan())
  vi.mocked(fetchBasePullPlan).mockResolvedValue({ action: 'pull', base: 'main', base_sha: 'old', remote: 'origin', before: 'old', after: 'new', digest: 'pull', files: [], blockers: [] })
  vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'haifa', state: 'ok', running: [] }] as never, totals: {} })
})
afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})
describe('Factory live run integration', () => {
  it.each(['init', 'pull'] as const)('cancels confirmation and blocks %s on SSE arrival, then unblocks on end', async action => {
    const w = mount(FactoryOperation, { props: { repoId: 'haifa', action }, attachTo: document.body })
    await flushPromises()
    await w.get('[data-test="factory-perform"]').trigger('click')
    expect(openDialog()).not.toBeNull()
    vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'haifa', state: 'ok', running: [{ run_id: 'live', process: 'alive' }] }] as never, totals: {} })
    FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, run_ids: ['live'] }))
    await new Promise(resolve => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20)); await flushPromises()
    expect(openDialog()).toBeNull()
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-test="factory-running"] a').attributes('href')).toBe('#/r/haifa/runs/live')
    vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'haifa', state: 'ok', running: [{ run_id: 'live', process: 'ended' }] }] as never, totals: {} })
    FakeEventSource.latest().emit('trace', traceEvent({ seq: 2, runs_changed: true, run_ids: ['live'] }))
    await new Promise(resolve => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20)); await flushPromises()
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeUndefined()
    expect(applyFactoryPlan).not.toHaveBeenCalled()
    expect(applyBasePull).not.toHaveBeenCalled()
  })

  it('keeps pending operation identities and task links until claim', async () => {
    const first = operation('operation-1', { task_id: 'T1' })
    const second = operation('operation-2', { task_id: 'T2', workflow: 'publish' })
    vi.mocked(fetchOverview).mockResolvedValue(overview([repo('haifa', { running: [first, second] })]))
    const w = mount(FactoryOperation, { props: { repoId: 'haifa', action: 'init' }, attachTo: document.body })
    await flushPromises()
    const rows = () => w.findAll('[data-test="factory-running"] a')
    expect(rows().map(r => r.attributes('href'))).toEqual(['#/r/haifa/backlog/T1', '#/r/haifa/backlog/T2'])
    expect(rows().map(r => r.text())).toEqual(['T1', 'T2'])
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    const secondElement = rows()[1].element
    vi.mocked(fetchOverview).mockResolvedValue(overview([repo('haifa', {
      running: [second, running({ run_id: 'claimed', task_id: 'T1', pause: 'paused' })],
    })]))
    FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, run_ids: ['claimed'] }))
    await new Promise(resolve => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20)); await flushPromises()
    expect(rows()[0].element).toBe(secondElement)
    expect(rows().map(r => r.attributes('href'))).toEqual(['#/r/haifa/backlog/T2', '#/r/haifa/runs/claimed'])
    expect(rows().map(r => r.text())).toEqual(['T2', 'claimed'])
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    expect(applyFactoryPlan).not.toHaveBeenCalled()
  })

})

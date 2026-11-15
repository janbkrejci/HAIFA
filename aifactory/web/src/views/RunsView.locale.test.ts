import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/lib/i18n'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, traceEvent } from '@/test/fakeEventSource'
import { detail, events, okResponse, prompts, runTotals, summary } from '@/test/runsFixtures'
import RunsView from './RunsView.vue'
import RetryRunButton from '@/components/runs/RetryRunButton.vue'
import FailureCard from '@/components/runs/FailureCard.vue'
import ChainPanel from '@/components/runs/ChainPanel.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import SwitchHarnessButton from '@/components/runs/SwitchHarnessButton.vue'
import CostTotals from '@/components/runs/CostTotals.vue'
import type { Chain } from '@/lib/chains'
import { openDialog, answerDialog } from '@/test/modal'

enableAutoUnmount(afterEach)

beforeEach(() => {
  setLocale('en')
  vi.stubGlobal('EventSource', FakeEventSource)
})
afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  setLocale('en')
})

it('switches locale with a selected phase and expanded event, then keeps receiving live updates', async () => {
  window.location.hash = '#/r/haifa/runs/r-ok/p1'
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  const data = detail({ state: 'running', ended_at: null })
  data.phases[1]!.status = 'running'
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith('/prompts')) return okResponse(prompts())
    if (url.includes('/events')) return okResponse({ events: events(), cursor: 3, has_more: false })
    if (url.includes('/tail')) return okResponse({
      run: { ...data.run, tokens: 9999 }, session: data.session, agents: [],
      events: [{ ...events()[1]!, event_id: 'live-event', rowid: 4, payload: { tool: 'Read', result_snippet: 'Živý výstup beze změn' } }],
      phases: [], gates: [], envelopes: [], usage_delta: { read: 1, written: 1 },
      cursors: { events: 4, phases: 2, gates: 2, envelopes: 1 }, has_more: false,
    })
    return okResponse(data)
  })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(RunsView)
  await flushPromises()
  const panel = wrapper.get('.phase-detail[data-phase="p1"]')
  await panel.get('[data-event="e2"] [data-test="event-toggle"]').trigger('click')
  await panel.get('[data-section="request"] [data-test="dsec-toggle"]').trigger('click')
  await panel.get('[data-section="prompts"] [data-test="dsec-toggle"]').trigger('click')
  await panel.get('[data-prompt="user"] [data-test="prompt-toggle"]').trigger('click')
  const before = fetchMock.mock.calls.length
  expect(wrapper.get('[data-test="pause-run"]').text()).toBe('Pause')
  expect(panel.text()).toContain('Request')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('.phase-detail[data-phase="p1"]').element).toBe(panel.element)
  expect(wrapper.get('[data-test="pause-run"]').text()).toBe('Pauza')
  expect(wrapper.get('.phase-detail[data-phase="p1"]').text()).toContain('Požadavek')
  expect(wrapper.get('[data-event="e2"] [data-test="event-body"]').text()).toContain("print('x')")
  expect(wrapper.text()).toContain('Navrhnout schéma.')
  expect(wrapper.get('[data-prompt="user"] .prompt-body').text()).toContain('Zadání prvního tasku.')
  expect(fetchMock.mock.calls.length).toBe(before)
  expect(window.location.hash).toBe('#/r/haifa/runs/r-ok/p1')

  FakeEventSource.latest().emit('trace', traceEvent({ run_ids: ['r-ok'], events: 4 }))
  await new Promise(resolve => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
  await flushPromises()
  expect(wrapper.find('[data-event="live-event"]').exists()).toBe(true)
  setLocale('en')
  await flushPromises()
  expect(wrapper.get('.phase-detail[data-phase="p1"]').element).toBe(panel.element)
  expect(wrapper.get('[data-test="pause-run"]').text()).toBe('Pause')
  expect(wrapper.find('[data-event="live-event"]').exists()).toBe(true)
  expect(wrapper.find('[data-event="e2"] [data-test="event-body"]').exists()).toBe(true)
  wrapper.unmount()
})

it('keeps a retry draft and translates a coded API failure already on screen', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({
    ok: false, data: null, error: { code: 'unknown_run', message: 'původní backendová hláška' },
  })))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(RetryRunButton, { props: { runId: 'r-ok' } })
  expect(wrapper.get('[data-test="retry-run"]').text()).toBe('Retry')
  await wrapper.get('[data-test="retry-run"]').trigger('click')
  await wrapper.get('[data-test="retry-note"]').setValue('Poznámku nepřekládat')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[data-test="retry-error"]').text()).toContain('The run was not found.')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="retry-run"]').text()).toBe('Navázat')
  expect(wrapper.get('[data-test="retry-error"]').text()).toContain('Běh nebyl nalezen.')
  expect(wrapper.get('[data-test="retry-note"]').element).toHaveProperty('value', 'Poznámku nepřekládat')
  setLocale('en')
  await flushPromises()
  expect(wrapper.get('[data-test="retry-error"]').text()).toContain('The run was not found.')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})

it('translates failure facts and pending confirmation without translating stored evidence', async () => {
  const run = summary({ state: 'failed', failure_kind: 'nothing_to_do',
    error: 'Původní chyba', failure_detail: { agent: 'builder', summary: 'Vše je již hotové.' },
  })
  const wrapper = mount(FailureCard, { props: { run } })
  expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('The agent had nothing to do')
  expect(wrapper.get('[data-test="failure-sentence"]').text()).toContain('Vše je již hotové.')
  await wrapper.get('[data-test="mark-done"]').trigger('click')
  expect(openDialog()?.textContent).toContain('Mark task')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Agent neměl co dělat')
  expect(wrapper.get('[data-test="failure-sentence"]').text()).toContain('Vše je již hotové.')
  expect(openDialog()?.textContent).toContain('Označit task')
  await answerDialog(false)
  wrapper.unmount()
})

it('updates list filters, costs and chain statuses in place', async () => {
  window.location.hash = '#/r/haifa/runs'
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  const chain: Chain = { chain_id: 'c1', task_id: 'T1', state: 'finished', stop: 'exhausted',
    max_parallel: 2, started_at: '', updated_at: '', ended_at: '', runs: [], running: 0,
    free_slots: 2, exclusive: [], skipped: [{ task_id: 'T2', reason: 'blocked', detail: 'Původní diagnostika', waits_on: ['T1'] }],
  }
  const fetchMock = vi.fn(async (url: string) => okResponse(url.endsWith('/chains') ? { chains: [chain] }
    : url.endsWith('/totals') ? runTotals() : { runs: [summary()], tasks: ['T1'], total: 1 }))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(RunsView)
  await flushPromises()
  const filter = wrapper.findAllComponents(SelectMenu)[0]!
  filter.vm.$emit('update:modelValue', 'running')
  await flushPromises()
  await wrapper.getComponent(CostTotals).get('[data-test="dsec-toggle"]').trigger('click')
  await flushPromises()
  expect(wrapper.getComponent(ChainPanel).text()).toContain('ended: nothing to start')
  const before = fetchMock.mock.calls.length
  setLocale('cs')
  await flushPromises()
  expect(wrapper.getComponent(ChainPanel).text()).toContain('skončil: není co spustit')
  expect(wrapper.getComponent(CostTotals).text()).toContain('Náklady')
  expect(filter.props('modelValue')).toBe('running')
  expect(filter.props('options')[0].label).toBe('Všechny stavy')
  expect(fetchMock.mock.calls.length).toBe(before)
  wrapper.unmount()
})

it('keeps the selected fallback harness while switching languages', async () => {
  const fetchMock = vi.fn(async () => okResponse({ run_id: 'r-ok', choices: [
    { harness: 'claude', model: 'model-a', thinking: null },
    { harness: 'pi', model: 'model-b', thinking: null },
  ] }))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(SwitchHarnessButton, { props: { runId: 'r-ok' } })
  await wrapper.get('[data-test="switch-harness"]').trigger('click')
  await flushPromises()
  const select = wrapper.getComponent(SelectMenu)
  select.vm.$emit('update:modelValue', 'pi')
  await flushPromises()
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="switch-harness"]').text()).toBe('Pokračovat s jiným harnessem')
  expect(select.props('modelValue')).toBe('pi')
  setLocale('en')
  await flushPromises()
  expect(select.props('modelValue')).toBe('pi')
  expect(wrapper.get('[data-test="switch-harness"]').text()).toBe('Continue with another harness')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})

it('keeps the busy-database retry action available in both languages using its code', async () => {
  window.location.hash = '#/r/haifa/runs'
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/chains')
    ? okResponse({ chains: [] })
    : new Response(JSON.stringify({ ok: false, data: null, error: {
      code: 'trace_db_locked', message: 'database is locked',
    } }))))
  const wrapper = mount(RunsView)
  await flushPromises()
  expect(wrapper.get('[data-test="retry"]').text()).toBe('Try again')
  expect(wrapper.get('[data-test="error"]').text()).toContain('The run database is busy.')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="retry"]').text()).toBe('Zkusit znovu')
  expect(wrapper.get('[data-test="error"]').text()).toContain('Databáze běhů je právě obsazená.')
  wrapper.unmount()
})

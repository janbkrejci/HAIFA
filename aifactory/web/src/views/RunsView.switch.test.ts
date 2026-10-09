import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunsView from './RunsView.vue'
import { detail, events, prompts } from '@/test/runsFixtures'
import { deferred, type Deferred } from '@/test/deferred'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, traceEvent } from '@/test/fakeEventSource'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function eventsPage() {
  return ok({ events: events(), cursor: 3, has_more: false })
}

function runOf(id: string, title: string) {
  return ok({ ...detail({ run_id: id, task_id: `T-${id}`, task_title: title, state: 'running' }) })
}

/** Every detail and events request waits for the test; prompts answer at once. */
function stubDeferredApi() {
  const runs = new Map<string, Deferred<Response>[]>()
  const evts = new Map<string, Deferred<Response>[]>()
  const take = (map: Map<string, Deferred<Response>[]>, id: string) => {
    const d = deferred<Response>()
    map.set(id, [...(map.get(id) ?? []), d])
    return d.promise
  }
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.endsWith('/prompts')) return ok(prompts())
    const m = /^\/api\/repos\/haifa\/runs\/([^/?]+)(\/events)?/.exec(url)
    if (!m) throw new Error(`unexpected ${url}`)
    return take(m[2] ? evts : runs, m[1])
  })
  vi.stubGlobal('fetch', fetchMock)
  const last = (map: Map<string, Deferred<Response>[]>, id: string) => {
    const list = map.get(id)
    if (!list?.length) throw new Error(`no request for ${id}`)
    return list[list.length - 1]
  }
  return {
    fetchMock,
    run: (id: string) => last(runs, id),
    events: (id: string) => last(evts, id),
  }
}

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/runs')
})

describe('RunsView switching runs', () => {
  it('drops the previous run at once and shows the detail before its events', async () => {
    go('#/r/haifa/runs/r-a')
    const api = stubDeferredApi()
    const wrapper = mount(RunsView)
    await flushPromises()
    api.run('r-a').resolve(runOf('r-a', 'Alpha'))
    api.events('r-a').resolve(eventsPage())
    await flushPromises()
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Alpha')

    go('#/r/haifa/runs/r-b/p1')
    await flushPromises()
    expect(wrapper.text()).not.toContain('Alpha')
    expect(wrapper.find('[data-test="task-label"]').exists()).toBe(false)
    const loading = wrapper.find('[data-test="detail-loading"]')
    expect(loading.exists()).toBe(true)
    expect(loading.text()).toContain('r-b')

    api.run('r-b').resolve(runOf('r-b', 'Beta'))
    await flushPromises()
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Beta')
    expect(wrapper.find('[data-test="events-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="phase-events-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-event="e1"]').exists()).toBe(false)

    api.events('r-b').resolve(eventsPage())
    await flushPromises()
    expect(wrapper.find('[data-test="events-loading"]').exists()).toBe(false)
    expect(wrapper.find('[data-event="e1"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps the newer run when the older answer arrives later', async () => {
    go('#/r/haifa/runs/r-a')
    const api = stubDeferredApi()
    const wrapper = mount(RunsView)
    await flushPromises()
    go('#/r/haifa/runs/r-b')
    await flushPromises()

    api.run('r-b').resolve(runOf('r-b', 'Beta'))
    api.events('r-b').resolve(eventsPage())
    await flushPromises()
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Beta')

    api.run('r-a').resolve(runOf('r-a', 'Alpha'))
    api.events('r-a').resolve(eventsPage())
    await flushPromises()
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Beta')
    expect(wrapper.text()).not.toContain('Alpha')
    expect(wrapper.find('[data-test="refresh"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('ignores an older run answer that arrives while the newer one still loads', async () => {
    go('#/r/haifa/runs/r-a')
    const api = stubDeferredApi()
    const wrapper = mount(RunsView)
    await flushPromises()
    go('#/r/haifa/runs/r-b')
    await flushPromises()
    api.run('r-a').resolve(runOf('r-a', 'Alpha'))
    api.events('r-a').resolve(eventsPage())
    await flushPromises()
    expect(wrapper.text()).not.toContain('Alpha')
    expect(wrapper.find('[data-test="detail-loading"]').text()).toContain('r-b')
    api.run('r-b').resolve(runOf('r-b', 'Beta'))
    api.events('r-b').resolve(eventsPage())
    await flushPromises()
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Beta')
    wrapper.unmount()
  })

  it('does not mix a pending live tail of the old run into the new one', async () => {
    go('#/r/haifa/runs/r-a')
    vi.stubGlobal('EventSource', FakeEventSource)
    const api = stubDeferredApi()
    const tail = deferred<Response>()
    const base = api.fetchMock.getMockImplementation()!
    api.fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
      url.includes('/tail') ? tail.promise : base(url, init),
    )
    const wrapper = mount(RunsView)
    await flushPromises()
    api.run('r-a').resolve(runOf('r-a', 'Alpha'))
    api.events('r-a').resolve(eventsPage())
    await flushPromises()
    FakeEventSource.latest().emit('trace', traceEvent({ run_ids: ['r-a'], events: 4 }))
    await new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
    await flushPromises()
    expect(api.fetchMock.mock.calls.some(([url]) => url.includes('/r-a/tail'))).toBe(true)

    go('#/r/haifa/runs/r-b/p1')
    await flushPromises()
    api.run('r-b').resolve(runOf('r-b', 'Beta'))
    api.events('r-b').resolve(ok({ events: [], cursor: 0, has_more: false }))
    await flushPromises()
    const [first] = events()
    tail.resolve(
      ok({
        run: detail({ run_id: 'r-a' }).run,
        session: null,
        events: [{ ...first, rowid: 9, event_id: 'e-old-live', type: 'tool_call', name: 'Grep', payload: { tool: 'Grep' } }],
        phases: [],
        gates: [],
        envelopes: [],
        agents: [],
        usage_delta: { read: 0, written: 0 },
        cursors: { events: 9, phases: 2, gates: 2, envelopes: 1 },
        has_more: false,
      }),
    )
    await flushPromises()
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Beta')
    expect(wrapper.find('[data-event="e-old-live"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('switching the phase of the same run does not reload it', async () => {
    go('#/r/haifa/runs/r-a/p1')
    const api = stubDeferredApi()
    const wrapper = mount(RunsView)
    await flushPromises()
    api.run('r-a').resolve(runOf('r-a', 'Alpha'))
    api.events('r-a').resolve(eventsPage())
    await flushPromises()
    const calls = () => api.fetchMock.mock.calls.filter(([url]) => !url.endsWith('/prompts')).length
    const before = calls()
    go('#/r/haifa/runs/r-a/p2')
    await flushPromises()
    expect(calls()).toBe(before)
    expect(wrapper.find('[data-test="task-label"]').text()).toContain('Alpha')
    expect(wrapper.find('[data-test="detail-loading"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="events-loading"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunsView from './RunsView.vue'
import { detail, events, prompts, runTotals, runsResponse } from '@/test/runsFixtures'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, traceEvent } from '@/test/fakeEventSource'
import { answerDialog } from '@/test/modal'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function fail(code: string, message: string, status: number) {
  return new Response(
    JSON.stringify({ ok: false, data: null, error: { code, message, path: null, id: null, issues: [] }, warnings: [] }),
    { status },
  )
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function debounce() {
  return new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
}

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/runs')
})

describe('RunsView', () => {
  it('loads the list, without state and task filters, and the costs only when opened', async () => {
    go('#/r/haifa/runs')
    const fetchMock = vi.fn(async (url: string) => ok(url === '/api/repos/haifa/runs/totals' ? runTotals() : runsResponse()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Běhy')
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs')
    expect(wrapper.findAll('tr[data-run]')).toHaveLength(2)
    // costs are folded and not loaded until opened
    expect(wrapper.find('[data-test="backlog-total"]').exists()).toBe(false)
    expect(fetchMock).not.toHaveBeenCalledWith('/api/repos/haifa/runs/totals')
    await wrapper.find('[data-section="costs"] [data-test="dsec-toggle"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/totals')
    expect(wrapper.find('[data-test="backlog-total"]').text()).toContain('$0.2600')
    expect(wrapper.find('[data-test="state-filter"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="task-filter"]').exists()).toBe(false)
    await wrapper.find('[data-test="view-archived"]').trigger('click')
    await flushPromises()
    // the list reloads, and with costs open the totals too
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs?archived=1')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/runs/totals')
    wrapper.unmount()
  })

  it('survives a response without runs', async () => {
    go('#/r/haifa/runs')
    vi.stubGlobal('fetch', vi.fn(async () => ok({ version: '0.1.0' })))
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.find('[data-test="no-runs"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows an API error', async () => {
    go('#/r/haifa/runs')
    vi.stubGlobal('fetch', vi.fn(async () => fail('invalid_config', 'bad config', 500)))
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.find('[data-test="error"]').text()).toContain('bad config')
    wrapper.unmount()
  })

  it('stops a running run and reloads the detail', async () => {
    go('#/r/haifa/runs/r-run')
    let state = 'running'
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        state = 'stopped'
        return ok({ run: detail({ run_id: 'r-run', state: 'stopped' }).run, signalled: [1], killed: [] })
      }
      if (url.includes('/events')) return ok({ events: events(), cursor: 3, has_more: false })
      return ok(detail({ run_id: 'r-run', state: state as 'running' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-run')
    const back = wrapper.find('a[data-test="back"]')
    expect(back.find('svg').exists()).toBe(true)
    expect(back.text()).toBe('všechny běhy')
    expect(back.attributes('href')).toBe('#/r/haifa/runs')
    await wrapper.find('[data-test="stop-run"]').trigger('click')
    await answerDialog(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-run/stop', { method: 'POST' })
    const gets = fetchMock.mock.calls.filter(([url, init]) => url === '/api/repos/haifa/runs/r-run' && !init)
    expect(gets).toHaveLength(2)
    expect(wrapper.find('[data-test="stop-run"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('zastaveno')
    wrapper.unmount()
  })

  it('pauses a running run and resumes the paused one', async () => {
    go('#/r/haifa/runs/r-run')
    let pause: 'paused' | null = null
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        pause = url.endsWith('/pause') ? 'paused' : null
        return ok({ run: detail({ run_id: 'r-run', state: 'running', pause }).run })
      }
      if (url.includes('/events')) return ok({ events: [], cursor: 0, has_more: false })
      return ok(detail({ run_id: 'r-run', state: 'running', pause }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    await wrapper.get('[data-test="pause-run"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-run/pause', { method: 'POST' })
    expect(wrapper.text()).toContain('pozastaveno')
    await wrapper.get('[data-test="resume-run"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-run/resume', { method: 'POST' })
    expect(wrapper.find('[data-test="pause-run"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('pozastaveno')
    wrapper.unmount()
  })

  it('reports a failed pause', async () => {
    go('#/r/haifa/runs/r-run')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return fail('run_not_running', 'run r-run is failed', 409)
      if (url.includes('/events')) return ok({ events: [], cursor: 0, has_more: false })
      return ok(detail({ run_id: 'r-run', state: 'running' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    await wrapper.get('[data-test="pause-run"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="error"]').text()).toContain('pozastavit')
    wrapper.unmount()
  })

  it('publishes a succeeded run without a PR and reloads the detail', async () => {
    go('#/r/haifa/runs/r-ok')
    let published = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        published = true
        return ok({ run: detail().run, pr: { url: 'https://example.test/pr/7', pr_id: '7', state: 'open' }, pr_error: null })
      }
      if (url.includes('/events')) return ok({ events: [], cursor: 0, has_more: false })
      return ok(published ? detail() : detail({ pr: null, pr_error: 'push_failed: RPC failed' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.get('[data-test="pr-error"]').text()).toContain('RPC failed')
    await wrapper.get('[data-test="publish-run"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-ok/publish', { method: 'POST' })
    expect(wrapper.find('[data-test="publish-run"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="pr-link"]').text()).toContain('#7')
    wrapper.unmount()
  })

  it('reports a publish whose push failed again', async () => {
    go('#/r/haifa/runs/r-ok')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return ok({ run: detail({ pr: null }).run, pr: null, pr_error: 'push_failed: hung up' })
      if (url.includes('/events')) return ok({ events: [], cursor: 0, has_more: false })
      return ok(detail({ pr: null, pr_error: 'push_failed: hung up' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    await wrapper.get('[data-test="publish-run"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toContain('PR se nepodařilo otevřít: push_failed: hung up')
    wrapper.unmount()
  })

  it('reports a failed stop', async () => {
    go('#/r/haifa/runs/r-run')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return fail('run_not_running', 'run r-run is failed', 409)
      if (url.includes('/events')) return ok({ events: [], cursor: 0, has_more: false })
      return ok(detail({ run_id: 'r-run', state: 'running' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    await wrapper.find('[data-test="stop-run"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.find('[data-test="error"]').text()).toContain('run r-run is failed')
    wrapper.unmount()
  })

  it('appends new trace rows through the rowid tail on a live trace event', async () => {
    go('#/r/haifa/runs/r-ok/p1')
    vi.stubGlobal('EventSource', FakeEventSource)
    const cursors = { events: 3, phases: 2, gates: 2, envelopes: 1 }
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('/tail')) {
        const [first] = events()
        return ok({
          run: detail().run,
          session: null,
          events: [{ ...first, rowid: 4, event_id: 'e-live', type: 'tool_call', name: 'Grep', payload: { tool: 'Grep' } }],
          phases: [],
          gates: [],
          envelopes: [],
          agents: [],
          usage_delta: { read: 0, written: 0 },
          cursors: { ...cursors, events: 4 },
          has_more: false,
        })
      }
      if (url.includes('/events')) return ok({ events: events(), cursor: 3, has_more: false })
      if (url.endsWith('/prompts')) return ok(prompts())
      if (url.startsWith('/api/repos/haifa/runs/r-ok')) return ok({ ...detail(), cursors })
      return ok(runsResponse())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.find('[data-event="e-live"]').exists()).toBe(false)
    const promptCalls = () => fetchMock.mock.calls.filter(([url]) => url.endsWith('/prompts')).length
    expect(promptCalls()).toBe(1)
    const eventCalls = () => fetchMock.mock.calls.filter(([url]) => url.includes('/events')).length
    const before = eventCalls()

    FakeEventSource.latest().emit('trace', traceEvent({ run_ids: ['r-other'] }))
    await debounce()
    await flushPromises()
    expect(fetchMock.mock.calls.some(([url]) => url.includes('/tail'))).toBe(false)

    FakeEventSource.latest().emit('trace', traceEvent({ run_ids: ['r-ok'], events: 4 }))
    await debounce()
    await flushPromises()
    const tails = fetchMock.mock.calls.filter(([url]) => url.includes('/tail'))
    expect(tails).toHaveLength(1)
    expect(tails[0][0]).toContain('/api/repos/haifa/runs/r-ok/tail?events=3&phases=2&gates=2&envelopes=1')
    expect(eventCalls()).toBe(before)
    expect(wrapper.find('[data-event="e-live"]').exists()).toBe(true)
    expect(promptCalls()).toBe(1)
    expect(wrapper.find('[data-test="refresh"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('quietly refetches the list when runs change', async () => {
    go('#/r/haifa/runs')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.fn(async (_url: string) => ok(runsResponse()))
    vi.stubGlobal('fetch', fetchMock)
    const runCalls = () => fetchMock.mock.calls.filter(([url]) => url.startsWith('/api/repos/haifa/runs')).length
    const chainCalls = () => fetchMock.mock.calls.filter(([url]) => url === '/api/repos/haifa/chains').length
    const wrapper = mount(RunsView)
    await flushPromises()
    expect([runCalls(), chainCalls()]).toEqual([1, 1])
    FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, task_ids: ['M01-S01-T01'] }))
    await debounce()
    await flushPromises()
    expect([runCalls(), chainCalls()]).toEqual([2, 2])
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/runs')
    wrapper.unmount()
  })

  it('shows the auto-continue chains above the list', async () => {
    go('#/r/haifa/runs')
    const chain = {
      chain_id: 'c1',
      task_id: 'M01-S01-T01',
      state: 'running',
      stop: null,
      max_parallel: 2,
      started_at: '',
      updated_at: '',
      ended_at: null,
      runs: [{ run_id: 'r-run', task_id: 'M01-S01-T01', state: 'running' }],
      running: 1,
      free_slots: 1,
      skipped: [{ task_id: 'M01-S01-T02', reason: 'writes_overlap', detail: 'PR u: src/a.py', waits_on: [] }],
      exclusive: [],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url === '/api/repos/haifa/chains' ? ok({ max_parallel_runs: 2, chains: [chain] }) : ok(runsResponse()),
      ),
    )
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.get('[data-test="chain-slots"]').text()).toContain('Sloty: 1/2 (volné 1)')
    expect(wrapper.get('[data-test="chain-skip"]').text()).toContain('překryv writes')
    wrapper.unmount()
  })

  it('hides an ended chain', async () => {
    go('#/r/haifa/runs')
    const chain = {
      chain_id: 'c1',
      task_id: 'M01-S01-T01',
      state: 'finished',
      stop: 'exhausted',
      max_parallel: 1,
      started_at: '',
      updated_at: '',
      ended_at: '',
      runs: [{ run_id: 'r-ok', task_id: 'M01-S01-T01', state: 'succeeded' }],
      running: 0,
      free_slots: 0,
      skipped: [],
      exclusive: [],
    }
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url === '/api/repos/haifa/chains') return ok({ max_parallel_runs: 1, chains: [chain] })
      if (url === '/api/repos/haifa/chains/c1/dismiss') return ok({ dismissed: 'c1' })
      return ok(runsResponse())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RunsView)
    await flushPromises()
    await wrapper.get('[data-test="chain-dismiss"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/chains/c1/dismiss', expect.objectContaining({ method: 'POST' }))
    expect(wrapper.find('[data-test="chain-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the list when the chains cannot be read', async () => {
    go('#/r/haifa/runs')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url === '/api/repos/haifa/chains' ? fail('internal_error', 'boom', 500) : ok(runsResponse()),
      ),
    )
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.find('[data-test="chain-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="error"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="task-label"]').length).toBeGreaterThan(0)
    wrapper.unmount()
  })

  describe('archiv', () => {
    function archiveServer() {
      let archivedIds: string[] = []
      const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const data = runsResponse()
        if (init?.method === 'POST') {
          if (url === '/api/repos/haifa/runs/archive-finished') {
            archivedIds = ['r-ok']
            return ok({ archived: ['r-ok'] })
          }
          if (url === '/api/repos/haifa/runs/delete-archived') {
            const deleted = archivedIds
            archivedIds = []
            return ok({ deleted })
          }
          const [, , , , , id, action] = url.split('/')
          if (action === 'archive') archivedIds = [...archivedIds, id!]
          if (action === 'unarchive' || action === 'delete') archivedIds = archivedIds.filter((x) => x !== id)
          return ok({ run: data.runs[1] })
        }
        const wantArchived = url.includes('archived=1')
        return ok({
          ...data,
          runs: data.runs
            .map((r) => ({ ...r, archived: archivedIds.includes(r.run_id) }))
            .filter((r) => r.archived === wantArchived),
        })
      })
      vi.stubGlobal('fetch', fetchMock)
      return fetchMock
    }

    const rows = (wrapper: ReturnType<typeof mount>) =>
      wrapper.findAll('tr[data-run]').map((r) => r.attributes('data-run'))

    it('archives the finished runs after a confirmation and lists them in the archived view', async () => {
      go('#/r/haifa/runs')
      const fetchMock = archiveServer()
      const wrapper = mount(RunsView)
      await flushPromises()
      expect(rows(wrapper)).toEqual(['r-run', 'r-ok'])

      await wrapper.find('[data-test="archive-finished"]').trigger('click')
      await answerDialog(false)
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)

      await wrapper.find('[data-test="archive-finished"]').trigger('click')
      await answerDialog(true)
      expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/archive-finished', { method: 'POST' })
      expect(rows(wrapper)).toEqual(['r-run'])

      await wrapper.find('[data-test="view-archived"]').trigger('click')
      await flushPromises()
      expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/runs?archived=1')
      expect(rows(wrapper)).toEqual(['r-ok'])

      await wrapper.find('[data-test="delete-archived"]').trigger('click')
      await answerDialog(true)
      expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/delete-archived', { method: 'POST' })
      expect(rows(wrapper)).toEqual([])
      expect(wrapper.find('[data-test="no-runs"]').text()).toBe('Žádné archivované běhy')
      wrapper.unmount()
    })

    it('archives, restores and deletes one run from its row', async () => {
      go('#/r/haifa/runs')
      const fetchMock = archiveServer()
      const wrapper = mount(RunsView)
      await flushPromises()
      await wrapper.find('tr[data-run="r-ok"] [data-test="archive"]').trigger('click')
      await flushPromises()
      expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-ok/archive', { method: 'POST' })
      expect(rows(wrapper)).toEqual(['r-run'])

      await wrapper.find('[data-test="view-archived"]').trigger('click')
      await flushPromises()
      await wrapper.find('tr[data-run="r-ok"] [data-test="unarchive"]').trigger('click')
      await flushPromises()
      expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-ok/unarchive', { method: 'POST' })
      expect(rows(wrapper)).toEqual([])

      await wrapper.find('[data-test="view-active"]').trigger('click')
      await flushPromises()
      await wrapper.find('tr[data-run="r-ok"] [data-test="archive"]').trigger('click')
      await flushPromises()
      await wrapper.find('[data-test="view-archived"]').trigger('click')
      await flushPromises()
      await wrapper.find('tr[data-run="r-ok"] [data-test="delete"]').trigger('click')
      await answerDialog(true)
      expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-ok/delete', { method: 'POST' })
      expect(rows(wrapper)).toEqual([])
      wrapper.unmount()
    })

    it('reports a failed archive', async () => {
      go('#/r/haifa/runs')
      vi.stubGlobal(
        'fetch',
        vi.fn(async (_url: string, init?: RequestInit) =>
          init?.method === 'POST' ? fail('run_running', 'run r-ok is still running', 409) : ok(runsResponse()),
        ),
      )
      const wrapper = mount(RunsView)
      await flushPromises()
      await wrapper.find('tr[data-run="r-ok"] [data-test="archive"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('[data-test="error"]').text()).toContain('run r-ok is still running')
      wrapper.unmount()
    })
  })
})

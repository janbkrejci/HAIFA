import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import BacklogView from './BacklogView.vue'
import {
  backlogData,
  containerDetail,
  containerGraph,
  expandTree,
  runCheck,
  runStart,
  taskDetail,
  taskNode,
} from '@/test/backlogFixtures'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, filesEvent, traceEvent } from '@/test/fakeEventSource'
import { chooseOption, openSelect, selectLabels } from '@/test/select'
import { deferred, type Deferred } from '@/test/deferred'
import { HIDE_DONE_KEY, resetTreeForTests } from '@/lib/backlog'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function fail(code: string, message: string, status: number, issues: unknown[] = []) {
  return new Response(
    JSON.stringify({ ok: false, data: null, error: { code, message, path: null, id: null, issues }, warnings: [] }),
    { status },
  )
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

const rejected = [{ code: 'unknown_ref', message: "unknown id 'NOPE'", path: 'backlog/x.md', id: 'T5' }]

function debounce() {
  return new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
}

beforeEach(() => {
  localStorage.clear()
  resetTreeForTests()
})

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/backlog')
})

describe('BacklogView', () => {
  it('saves generated advice from task detail, refreshes catalog, detail and the config banner', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    vi.stubGlobal('EventSource', FakeEventSource)
    let saved = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/workflow-advice')) return ok({ job_id: 'view-job' })
      if (url.endsWith('/workflow-advice/view-job')) return ok({ state: 'succeeded', recommendation: {
        decision: 'new', workflow_name: 'research', workflow_yaml: 'name: research\nsteps: [plan]',
        reason: 'Research is sufficient', outline: [{ name: 'plan' }],
      } })
      if (url.endsWith('/edit')) {
        expect(JSON.parse(init?.body as string)).toEqual({ workflow: 'research', workflow_advice_id: 'view-job' })
        saved = true
        return ok({ task: taskNode({ own_workflow: 'research', workflow: 'research' }), requires_config_commit: true })
      }
      if (url.endsWith('/tasks/M01-S01-T02')) {
        const detail = taskDetail()
        if (saved) detail.task = { ...detail.task, own_workflow: 'research', workflow: 'research' }
        return ok(detail)
      }
      return ok(backlogData({ workflows: saved ? ['plan', 'research'] : ['plan'] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    const opener = wrapper.findAll('button').find((button) => button.text() === 'Upravit a navrhnout workflow')!
    await opener.trigger('click')
    await wrapper.get('[data-test="workflow-advice"] button').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/workflow-advice'))).toBe(true)
    const listGets = () => fetchMock.mock.calls.filter(([url]) => url === '/api/repos/haifa/backlog').length
    const detailGets = () => fetchMock.mock.calls.filter(([url]) => url.endsWith('/tasks/M01-S01-T02')).length
    const beforeList = listGets()
    const beforeDetail = detailGets()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(saved).toBe(true)
    expect(listGets()).toBeGreaterThan(beforeList)
    expect(detailGets()).toBeGreaterThan(beforeDetail)
    // the new workflow waits for its commit: the banner of the repo screen says so, no own notice
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/repos/haifa/config/status')).toBe(true)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="workflow"]').text()).toContain('research')
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })

  it('waits for fresh steps before opening a new task from a graph', async () => {
    go('#/r/haifa/backlog/graph/M01-S01')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fresh = deferred<Response>()
    let opening = false
    const list = backlogData()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/graph')) return ok(containerGraph())
      if (url === '/api/repos/haifa/backlog') {
        return opening ? fresh.promise : ok({ ...list, steps: list.steps.slice(0, 1) })
      }
      return ok(containerDetail())
    }))
    const wrapper = mount(BacklogView)
    await flushPromises()
    opening = true
    go('#/r/haifa/backlog/new')
    await flushPromises()
    expect(wrapper.find('[data-test="step"]').exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.find('[data-test="new-task-loading"]').exists()).toBe(true)
    fresh.resolve(ok(list))
    await flushPromises()
    expect(wrapper.find('[data-test="new-task-loading"]').exists()).toBe(false)
    await chooseOption(wrapper, '[data-test="step"]', 'M02-S01')
    await wrapper.get('[data-test="title"]').setValue('CSV export')
    expect(wrapper.get('[data-test="step"]').text()).toContain('M02-S01')
    expect((wrapper.get('[data-test="title"]').element as HTMLInputElement).value).toBe('CSV export')
    wrapper.unmount()
  })

  it('keeps the new-task draft and open dropdown during a live steps refresh', async () => {
    go('#/r/haifa/backlog/new')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fresh = deferred<Response>()
    const list = backlogData()
    let refreshing = false
    vi.stubGlobal('fetch', vi.fn(async () => refreshing ? fresh.promise : ok(list)))
    const wrapper = mount(BacklogView)
    await flushPromises()
    await chooseOption(wrapper, '[data-test="step"]', 'M02-S01')
    await wrapper.get('[data-test="title"]').setValue('CSV export')
    await openSelect(wrapper, '[data-test="step"]')
    const form = wrapper.get('form').element
    refreshing = true
    FakeEventSource.latest().emit('files', filesEvent(['backlog/M03/index.md']))
    await debounce()
    await flushPromises()
    expect(wrapper.get('[data-test="step"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="refresh"] svg').classes()).not.toContain('spin')
    fresh.resolve(ok({ ...list, steps: [...list.steps, { id: 'M03-S01', title: 'New', path: 'backlog/M03/S01', project: 'M03' }] }))
    await flushPromises()
    expect(wrapper.get('form').element).toBe(form)
    expect(wrapper.get('[data-test="step"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="step"]').text()).toContain('M02-S01')
    expect((wrapper.get('[data-test="title"]').element as HTMLInputElement).value).toBe('CSV export')
    await chooseOption(wrapper, '[data-test="step"]', 'M03-S01')
    wrapper.unmount()
  })

  it('keeps stale steps hidden after a failed new-task load until retry succeeds', async () => {
    go('#/r/haifa/backlog')
    vi.stubGlobal('EventSource', FakeEventSource)
    let failed = false
    vi.stubGlobal('fetch', vi.fn(async () => failed ? fail('unavailable', 'offline', 503) : ok(backlogData())))
    const wrapper = mount(BacklogView)
    await flushPromises()
    failed = true
    go('#/r/haifa/backlog/new')
    await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.get('[data-test="error"]').text()).toContain('offline')
    failed = false
    await wrapper.get('[data-test="refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('form').exists()).toBe(true)
    wrapper.unmount()
  })

  it('loads the tree and switches to kanban, without a status filter', async () => {
    go('#/r/haifa/backlog')
    expandTree()
    const fetchMock = vi.fn(async (_url: string) => ok(backlogData()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Backlog')
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog')
    expect(wrapper.find('[data-test="tree"]').exists()).toBe(true)
    expect(wrapper.findAll('a.task-link')).toHaveLength(4)
    await wrapper.find('[data-test="mode-kanban"]').trigger('click')
    // the seven board states and Odloženo
    expect(wrapper.findAll('[data-column]')).toHaveLength(8)
    expect(wrapper.find('[data-test="owner-filter"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="state-filter"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.every(([url]) => !url.includes('status='))).toBe(true)
    wrapper.unmount()
  })

  it('reports backlog problems and load errors', async () => {
    go('#/r/haifa/backlog')
    vi.stubGlobal('fetch', vi.fn(async () => ok(backlogData({ issues: rejected }))))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="problems"]').text()).toContain('1')
    wrapper.unmount()

    vi.stubGlobal('fetch', vi.fn(async () => fail('invalid_config', 'bad config', 500)))
    const broken = mount(BacklogView)
    await flushPromises()
    expect(broken.find('[data-test="error"]').text()).toContain('bad config')
    broken.unmount()
  })

  it('survives a response without a backlog', async () => {
    go('#/r/haifa/backlog')
    vi.stubGlobal('fetch', vi.fn(async () => ok({ version: '0.1.0' })))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="empty-tree"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('loads a task detail and reloads it after a write', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return ok({ action: 'link', changed: true, path: 'x', task: taskNode(), issues: [] })
      if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/tasks/M01-S01-T02')
    const back = wrapper.find('a[data-test="back"]')
    expect(back.find('svg').exists()).toBe(true)
    expect(back.text()).toBe('backlog')
    expect(back.attributes('href')).toBe('#/r/haifa/backlog')
    expect(wrapper.find('[data-test="task-title"]').text()).toBe('Loader')
    await wrapper.find('[data-test="unlink-M01-S01-T01"]').trigger('click')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/backlog/tasks/M01-S01-T02/link')
    expect(post?.[1]?.body).toBe('{"depends_on":["M01-S01-T01"],"remove":true}')
    const gets = fetchMock.mock.calls.filter(([url, init]) => url === '/api/repos/haifa/backlog/tasks/M01-S01-T02' && !init)
    expect(gets).toHaveLength(2)
    wrapper.unmount()
  })

  it('shows a rejected write with its issues and keeps the detail', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return fail('backlog_invalid', 'change rejected', 422, rejected)
      if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="link-input"]').setValue('NOPE')
    await wrapper.find('[data-test="link-add"]').trigger('click')
    await flushPromises()
    const error = wrapper.find('[data-test="write-error"]')
    expect(error.text()).toContain('change rejected')
    expect(error.find('[data-issue="unknown_ref"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="task-title"]').text()).toBe('Loader')
    wrapper.unmount()
  })

  it('creates a task and navigates to it', async () => {
    go('#/r/haifa/backlog/new')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return ok({ action: 'add', changed: true, path: 'x', task: taskNode({ id: 'M01-S01-T05' }), issues: [] })
      }
      if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog')
    await wrapper.find('[data-test="title"]').setValue('Nový task')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/backlog/tasks')
    expect(post?.[1]?.body).toBe('{"step":"M01-S01","title":"Nový task"}')
    expect(window.location.hash).toBe('#/r/haifa/backlog/M01-S01-T05')
    wrapper.unmount()
  })

  it('keeps the new-task form filled after a rejected add', async () => {
    go('#/r/haifa/backlog/new')
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? fail('backlog_invalid', 'change rejected', 422, rejected) : ok(backlogData()),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="title"]').setValue('Broken')
    await wrapper.find('[data-test="depends"]').setValue('NOPE')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="write-error"] [data-issue="unknown_ref"]').exists()).toBe(true)
    expect((wrapper.find('[data-test="title"]').element as HTMLInputElement).value).toBe('Broken')
    expect(window.location.hash).toBe('#/r/haifa/backlog/new')
    wrapper.unmount()
  })
  it('shows the graph of a step without its own auto-continue switches, Nový task in the step', async () => {
    go('#/r/haifa/backlog/graph/M01-S01')
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/graph')) return ok(containerGraph())
      if (url.endsWith('/containers/M01-S01')) return ok(containerDetail())
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/containers/M01-S01/graph')
    expect(fetchMock).not.toHaveBeenCalledWith('/api/repos/haifa/backlog/tasks/graph')
    expect(wrapper.find('[data-test="graph-title"]').text()).toBe('Model')
    expect(wrapper.find('a[data-node="M01-S01-T02"]').attributes('href')).toBe('#/r/haifa/backlog/M01-S01-T02')
    // the switches live in the Nastavení panel (and the tree), not twice on the page
    expect(wrapper.find('[data-test="auto-toggle"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="merge-toggle"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="container-settings"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="new-task"]').attributes('href')).toBe('#/r/haifa/backlog/new/M01-S01')
    wrapper.unmount()
  })

  it('opens the new task form with the step of the link preselected', async () => {
    go('#/r/haifa/backlog/new/M02-S01')
    vi.stubGlobal('fetch', vi.fn(async () => ok(backlogData())))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.get('[data-test="step"]').text()).toContain('M02-S01')
    wrapper.unmount()
  })

  it('reorders the kanban queue at once and saves it, undoing a failed save', async () => {
    go('#/r/haifa/backlog')
    const t4 = taskNode({ id: 'M01-S01-T04', title: 'Extra', path: 'backlog/M01-core/S01-model/M01-S01-T04-extra.md' })
    const list = backlogData()
    list.tasks = [...list.tasks, t4]
    let failing = false
    const gate = deferred<Response>()
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return failing ? fail('db_busy', 'database is locked', 503) : gate.promise
      return ok(list)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.get('[data-test="mode-kanban"]').trigger('click')
    const ready = () => wrapper.findAll('[data-column="ready"] [data-card]').map((c) => c.attributes('data-card'))
    expect(ready()).toEqual(['M01-S01-T02', 'M01-S01-T04'])
    await wrapper.get('[data-item="M01-S01-T04"] [data-test="move-up"]').trigger('click')
    // optimistic: the new order shows while the save runs
    expect(ready()).toEqual(['M01-S01-T04', 'M01-S01-T02'])
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/repos/haifa/backlog/queue/order')
    expect(post[1]?.body).toBe('{"order":["M01-S01-T04","M01-S01-T02"]}')
    gate.resolve(ok({ order: ['M01-S01-T04', 'M01-S01-T02'] }))
    await flushPromises()
    expect(fetchMock.mock.calls.filter(([url, init]) => url === '/api/repos/haifa/backlog' && !init?.method).length).toBe(2)

    failing = true
    await wrapper.get('[data-item="M01-S01-T02"] [data-test="exclude-toggle"]').trigger('click')
    await flushPromises()
    const exclude = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST').at(-1)!
    expect(exclude[0]).toBe('/api/repos/haifa/backlog/tasks/M01-S01-T02/auto-exclude')
    expect(exclude[1]?.body).toBe('{"excluded":true}')
    // the failed save is undone and reported like other errors of the view
    expect(wrapper.find('[data-column="deferred"] [data-card="M01-S01-T02"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="error"]').text()).toContain('Frontu se nepodařilo uložit')
    wrapper.unmount()
  })

  it('excludes the open task from auto continue in its detail', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    let excluded = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        excluded = true
        return ok({ task_id: 'M01-S01-T02', excluded: true })
      }
      if (url.startsWith('/api/repos/haifa/backlog/tasks/')) {
        const detail = taskDetail()
        return ok({ ...detail, task: { ...detail.task, auto_excluded: excluded } })
      }
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.get('[data-test="auto-queue-state"]').text()).toBe('ve frontě')
    await wrapper.get('[data-test="auto-queue-toggle"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/repos/haifa/backlog/tasks/M01-S01-T02/auto-exclude',
      expect.objectContaining({ method: 'POST', body: '{"excluded":true}' }),
    )
    expect(wrapper.get('[data-test="auto-queue-state"]').text()).toBe('odloženo')
    wrapper.unmount()
  })

  it('lists the problems of the backlog with a Czech count', async () => {
    go('#/r/haifa/backlog')
    const issues = [...rejected, { ...rejected[0], id: 'T6' }]
    vi.stubGlobal('fetch', vi.fn(async () => ok(backlogData({ issues }))))
    const wrapper = mount(BacklogView)
    await flushPromises()
    const problems = wrapper.get('[data-test="problems"]')
    expect(problems.text()).toContain('Backlog má 2 problémy.')
    expect(problems.findAll('[data-issue="unknown_ref"]')).toHaveLength(2)
    expect(problems.text()).not.toContain('factory backlog check')
    wrapper.unmount()
  })

  it('tells a hiding filter apart from an empty backlog and clears it', async () => {
    go('#/r/haifa/backlog')
    localStorage.setItem(HIDE_DONE_KEY, '1')
    resetTreeForTests()
    const data = backlogData()
    const done = (t: (typeof data.tasks)[number]) => ({ ...t, board_state: 'done' as const })
    const items = JSON.parse(JSON.stringify(data.items).replace(/"board_state":"[a-z ]+"/g, '"board_state":"done"'))
    vi.stubGlobal('fetch', vi.fn(async () => ok({ ...data, items, tasks: data.tasks.map(done) })))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="empty-tree"]').exists()).toBe(false)
    await wrapper.get('[data-test="clear-filter"]').trigger('click')
    expect(wrapper.find('[data-test="tree"]').exists()).toBe(true)
    expect(localStorage.getItem(HIDE_DONE_KEY)).toBe('0')
    wrapper.unmount()
  })

  it('creates a project from the backlog and opens its graph', async () => {
    go('#/r/haifa/backlog')
    const created = containerDetail({ id: 'M05', title: 'Dup', level: 'module', parent: null })
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url === '/api/repos/haifa/backlog/containers') {
        const body = JSON.parse(String(init.body)) as { id: string }
        if (body.id === 'M01') return fail('backlog_invalid', "id 'M01' exists already", 422, [{ code: 'duplicate_id', message: 'dup', path: 'backlog/M01-x/index.md', id: 'M01' }])
        return ok({ action: 'add', changed: true, path: 'backlog/M05-export/index.md', container: created.container, issues: [] })
      }
      if (url === '/api/repos/haifa/backlog/containers/M05/graph') {
        return ok(containerGraph({ container: { ...containerGraph().container, id: 'M05', title: 'Dup', level: 'module' }, nodes: [], edges: [] }))
      }
      if (url === '/api/repos/haifa/backlog/containers/M05') return ok(created)
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.get('[data-test="new-project"]').attributes('href')).toBe('#/r/haifa/backlog/new-container')
    go('#/r/haifa/backlog/new-container')
    await flushPromises()
    expect(wrapper.get('[data-test="container-form"]').attributes('data-level')).toBe('module')
    await wrapper.get('[data-test="container-id"]').setValue('M01')
    await wrapper.get('[data-test="container-title"]').setValue('Dup')
    await wrapper.get('[data-test="container-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="write-error"] [data-issue="duplicate_id"]').exists()).toBe(true)
    expect(window.location.hash).toBe('#/r/haifa/backlog/new-container')
    await wrapper.get('[data-test="container-id"]').setValue('M05')
    await wrapper.get('[data-test="container-form"]').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST').at(-1)
    expect(post?.[1]?.body).toBe('{"id":"M05","title":"Dup"}')
    expect(window.location.hash).toBe('#/r/haifa/backlog/graph/M05')
    await vi.waitFor(() => expect(wrapper.get('[data-test="graph-title"]').text()).toBe('Dup'))
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/containers/M05/graph')
    wrapper.unmount()
  })

  it('offers step creation in tree and kanban, selects a project and submits to the existing API', async () => {
    go('#/r/haifa/backlog')
    const created = containerDetail({ id: 'M02-S09', title: 'Export', parent: 'M02' })
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return ok({
        action: 'add', changed: true, path: 'x',
        container: created.container, issues: [],
      })
      if (url.endsWith('/M02-S09/graph')) return ok(containerGraph({
        container: { ...containerGraph().container, id: 'M02-S09', title: 'Export' },
        nodes: [], edges: [],
      }))
      if (url.endsWith('/containers/M02-S09')) return ok(created)
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.get('[data-test="new-step"]').text()).toContain('Nový step')
    await wrapper.get('[data-test="mode-kanban"]').trigger('click')
    go(wrapper.get('[data-test="new-step"]').attributes('href')!)
    await flushPromises()
    expect(window.location.hash).toBe('#/r/haifa/backlog/new-step')
    expect(wrapper.find('[data-test="container-form"]').exists()).toBe(false)
    expect(await selectLabels(wrapper, '[data-test="step-project"]')).toEqual(['M01 – Core', 'M02 – Web'])
    await chooseOption(wrapper, '[data-test="step-project"]', 'M01')
    expect(wrapper.get('[data-test="container-form"]').attributes('data-level')).toBe('step')
    // the next code after the steps of the project
    expect(wrapper.get('[data-test="container-id"]').attributes('placeholder')).toBe('M01-S02')
    await wrapper.get('[data-test="container-id"]').setValue('M01-S09')
    await chooseOption(wrapper, '[data-test="step-project"]', 'M02')
    expect(wrapper.get<HTMLInputElement>('[data-test="container-id"]').element.value).toBe('')
    expect(wrapper.get('[data-test="container-parent"]').text()).toContain('M02 · Web')
    await wrapper.get('[data-test="container-id"]').setValue('M02-S09')
    await wrapper.get('[data-test="container-title"]').setValue('Export')
    await wrapper.get('[data-test="container-form"]').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/backlog/containers')
    expect(JSON.parse(post?.[1]?.body as string)).toEqual({ id: 'M02-S09', title: 'Export', parent: 'M02' })
    expect(window.location.hash).toBe('#/r/haifa/backlog/graph/M02-S09')
    await vi.waitFor(() => expect(wrapper.get('[data-test="graph-title"]').text()).toBe('Export'))
    wrapper.unmount()
  })

  it('keeps the step draft while refreshing the project list', async () => {
    go('#/r/haifa/backlog/new-step')
    const pending = deferred<Response>()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok(backlogData()))
      .mockReturnValueOnce(pending.promise)
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    await chooseOption(wrapper, '[data-test="step-project"]', 'M01')
    await wrapper.get('[data-test="container-id"]').setValue('M01-S09')
    await wrapper.get('[data-test="container-title"]').setValue('Draft')
    await wrapper.get('[data-test="refresh"]').trigger('click')
    expect(wrapper.get<HTMLInputElement>('[data-test="container-id"]').element.value).toBe('M01-S09')
    pending.resolve(ok(backlogData()))
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[data-test="container-id"]').element.value).toBe('M01-S09')
    expect(wrapper.get<HTMLInputElement>('[data-test="container-title"]').element.value).toBe('Draft')
    wrapper.unmount()
  })

  it('keeps step validation errors in the form and cancels back to the backlog', async () => {
    go('#/r/haifa/backlog/new-step')
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? fail('duplicate_id', 'duplicate step', 409) : ok(backlogData()),
    ))
    const wrapper = mount(BacklogView)
    await flushPromises()
    await chooseOption(wrapper, '[data-test="step-project"]', 'M01')
    await wrapper.get('[data-test="container-id"]').setValue('M01-S01')
    await wrapper.get('[data-test="container-title"]').setValue('Duplicate')
    await wrapper.get('[data-test="container-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-test="write-error"]').text()).toContain('duplicate step')
    expect(wrapper.get<HTMLInputElement>('[data-test="container-title"]').element.value).toBe('Duplicate')
    await wrapper.get('[data-test="container-cancel"]').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/backlog')
    wrapper.unmount()
  })

  it('waits for the project list and offers project creation for an empty backlog', async () => {
    go('#/r/haifa/backlog/new-step')
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const wrapper = mount(BacklogView)
    expect(wrapper.find('[data-test="new-step-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="step-project"]').exists()).toBe(false)
    pending.resolve(ok(backlogData({ items: [], tasks: [], steps: [] })))
    await flushPromises()
    expect(wrapper.get('[data-test="new-step-empty"] a').attributes('href')).toBe('#/r/haifa/backlog/new-container')
    expect(wrapper.find('[data-test="container-form"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('omits step creation when the configured project holds tasks directly', async () => {
    go('#/r/haifa/backlog')
    vi.stubGlobal('fetch', vi.fn(async () => ok(backlogData({ levels: ['project', 'task'] }))))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="new-step"]').exists()).toBe(false)
    go('#/r/haifa/backlog/new-step')
    await flushPromises()
    expect(wrapper.get('[data-test="no-child-level"]').text()).toContain('tasky')
    expect(wrapper.find('[data-test="container-form"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers a new step on a module graph and sends it with its parent', async () => {
    go('#/r/haifa/backlog/graph/M01')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return ok({ action: 'add', changed: true, path: 'x', container: containerDetail({ id: 'M01-S09' }).container, issues: [] })
      }
      if (url.endsWith('/graph')) {
        const graph = containerGraph()
        return ok({ ...graph, container: { ...graph.container, id: 'M01', level: 'module' } })
      }
      if (url === '/api/repos/haifa/backlog/containers/M01') return ok(containerDetail({ id: 'M01', level: 'module' }))
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    const link = wrapper.get('[data-test="new-step"]')
    expect(link.attributes('href')).toBe('#/r/haifa/backlog/new-container/M01')
    expect(link.text()).toContain('Nový step')
    go('#/r/haifa/backlog/new-container/M01')
    await flushPromises()
    expect(wrapper.get('[data-test="container-parent"]').text()).toContain('M01 · Core')
    await wrapper.get('[data-test="container-id"]').setValue('M01-S09')
    await wrapper.get('[data-test="container-title"]').setValue('Nový')
    await wrapper.get('[data-test="container-form"]').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post?.[1]?.body).toBe('{"id":"M01-S09","title":"Nový","parent":"M01"}')
    expect(window.location.hash).toBe('#/r/haifa/backlog/graph/M01-S09')
    wrapper.unmount()
  })

  it('shows the settings of a step and saves a change through the API', async () => {
    go('#/r/haifa/backlog/graph/M01-S01')
    let workflow = 'plan'
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/edit')) {
        workflow = (JSON.parse(String(init.body)) as { workflow: string }).workflow
        const detail = containerDetail({ own: { workflow } }).container
        detail.effective.workflow = { ...detail.effective.workflow, value: workflow }
        return ok({ action: 'edit', changed: true, path: 'x', container: detail, issues: [] })
      }
      if (url.endsWith('/graph')) return ok(containerGraph())
      if (url === '/api/repos/haifa/backlog/containers/M01-S01') return ok(containerDetail({ own: { workflow } }))
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    // a step holds tasks only: no Nový step
    expect(wrapper.find('[data-test="new-step"]').exists()).toBe(false)
    const settings = wrapper.get('[data-test="container-settings"]')
    expect(settings.get('[data-test="value-workflow"]').text()).toContain('plan')
    await chooseOption(wrapper, '[data-test="edit-workflow"]', 'custom-flow')
    await wrapper.get('[data-test="container-settings"]').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/backlog/containers/M01-S01/edit')
    expect(post?.[1]?.body).toBe('{"workflow":"custom-flow"}')
    expect(wrapper.get('[data-test="value-workflow"]').text()).toContain('custom-flow')
    expect(wrapper.get('[data-test="settings-save"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('reports an unknown container', async () => {
    go('#/r/haifa/backlog/graph/M09')
    vi.stubGlobal('fetch', vi.fn(async () => fail('unknown_container', "no module or step 'M09'", 404)))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="error"]').text()).toContain("no module or step 'M09'")
    wrapper.unmount()
  })

  it('checks and starts a run with a note, then with --force, and opens the started run', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    let first = true
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/run')) {
        if (first) {
          first = false
          return fail('unmet_dependencies', 'task depends on work not done', 409)
        }
        return new Response(JSON.stringify({ ok: true, data: runStart({ force: true }), error: null, warnings: [] }), { status: 202 })
      }
      if (url.endsWith('/run-check')) return ok(runCheck())
      if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/tasks/M01-S01-T02/run-check')
    await wrapper.find('[data-test="run-note"]').setValue('z UI')
    await wrapper.find('[data-test="run-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="run-dialog"] [data-test="write-error"]').text()).toContain('depends on work')
    await wrapper.find('[data-test="run-force"]').trigger('click')
    await flushPromises()
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(posts.map(([url]) => url)).toEqual([
      '/api/repos/haifa/backlog/tasks/M01-S01-T02/run',
      '/api/repos/haifa/backlog/tasks/M01-S01-T02/run',
    ])
    expect(posts[0]?.[1]?.body).toBe('{"note":"z UI","force":false}')
    expect(posts[1]?.[1]?.body).toBe('{"note":"z UI","force":true}')
    // a started run opens its detail
    expect(window.location.hash).toBe('#/r/haifa/runs/r-9')
    const gets = fetchMock.mock.calls.filter(([url, init]) => url === '/api/repos/haifa/backlog/tasks/M01-S01-T02' && !init)
    expect(gets).toHaveLength(1)
    wrapper.unmount()
  })

  it('commits the backlog from the run dialog and checks the run again', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    let committed = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url === '/api/repos/haifa/backlog/commit') {
        committed = true
        return ok({ committed: true, commit: 'abc', base: 'main', paths: ['backlog/x.md'], pushed: false })
      }
      if (url.endsWith('/run-check')) return ok(runCheck({ in_base: committed }))
      if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
      return ok(backlogData())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="not-in-base"]').exists()).toBe(true)
    await wrapper.find('[data-test="commit-backlog"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/commit', expect.objectContaining({ method: 'POST' }))
    const checks = fetchMock.mock.calls.filter(([url]) => url.endsWith('/run-check'))
    expect(checks).toHaveLength(2)
    expect(wrapper.find('[data-test="not-in-base"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="run-start"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('refreshes only the touched parts on a live files event', async () => {
    go('#/r/haifa/backlog/M01-S01-T02')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.fn(async (url: string) =>
      url.startsWith('/api/repos/haifa/backlog/tasks/') ? ok(taskDetail()) : ok(backlogData()),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    const count = (prefix: string) =>
      fetchMock.mock.calls.filter(([url]) => url === prefix).length
    expect(count('/api/repos/haifa/backlog/tasks/M01-S01-T02')).toBe(1)
    expect(count('/api/repos/haifa/backlog')).toBe(1)

    await wrapper.find('[data-test="edit"]').trigger('click')
    FakeEventSource.latest().emit(
      'files',
      filesEvent(['backlog/M01-core/S01-model/M01-S01-T01-schema.md']),
    )
    await debounce()
    await flushPromises()
    expect(count('/api/repos/haifa/backlog')).toBe(2)
    expect(count('/api/repos/haifa/backlog/tasks/M01-S01-T02')).toBe(1)
    expect(wrapper.text()).not.toContain('Načítám')

    FakeEventSource.latest().emit(
      'files',
      filesEvent(['backlog/M01-core/S01-model/M01-S01-T02-loader.md']),
    )
    await debounce()
    await flushPromises()
    expect(count('/api/repos/haifa/backlog')).toBe(3)
    expect(count('/api/repos/haifa/backlog/tasks/M01-S01-T02')).toBe(2)
    // the edit form stays open over a live refresh of the same task
    expect(wrapper.find('form').exists()).toBe(true)

    FakeEventSource.latest().emit('files', filesEvent(['.factory/agents.yaml'], ['factory']))
    FakeEventSource.latest().emit('trace', traceEvent({ run_ids: ['r-1'] }))
    await debounce()
    await flushPromises()
    expect(count('/api/repos/haifa/backlog')).toBe(3)

    FakeEventSource.latest().emit(
      'trace',
      traceEvent({ runs_changed: true, task_ids: ['M01-S01-T02'] }),
    )
    await debounce()
    await flushPromises()
    expect(count('/api/repos/haifa/backlog')).toBe(4)
    expect(count('/api/repos/haifa/backlog/tasks/M01-S01-T02')).toBe(3)
    wrapper.unmount()
  })

  it('refreshes the graph only when its module changes', async () => {
    go('#/r/haifa/backlog/graph/M01-S01')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.fn(async (_url: string) => ok(containerGraph()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    const graphCalls = () =>
      fetchMock.mock.calls.filter(([url]) => url.includes('/graph')).length
    expect(graphCalls()).toBe(1)
    FakeEventSource.latest().emit('files', filesEvent(['backlog/M02-ui/index.md']))
    await debounce()
    await flushPromises()
    expect(graphCalls()).toBe(1)
    FakeEventSource.latest().emit(
      'files',
      filesEvent(['backlog/M01-core/S01-model/M01-S01-T09-new.md']),
    )
    await debounce()
    await flushPromises()
    expect(graphCalls()).toBe(2)
    wrapper.unmount()
  })
  describe('switching the open task', () => {
    const A = 'M01-S01-T02'
    const B = 'M01-S01-T03'

    function slowFetch() {
      const pending: Record<string, Deferred<Response>[]> = {}
      const fetchMock = vi.fn((url: string) => {
        if (url === '/api/repos/haifa/backlog') return Promise.resolve(ok(backlogData()))
        const d = deferred<Response>()
        ;(pending[url] ??= []).push(d)
        return d.promise
      })
      vi.stubGlobal('fetch', fetchMock)
      const answer = (id: string, index = 0) =>
        pending[`/api/repos/haifa/backlog/tasks/${id}`][index].resolve(
          ok(taskDetail({ task: taskNode({ id, title: `Title ${id}` }) })),
        )
      return { pending, fetchMock, answer }
    }

    it('hides the previous task at once and shows the new id loading', async () => {
      go(`#/r/haifa/backlog/${A}`)
      const api = slowFetch()
      const wrapper = mount(BacklogView)
      api.answer(A)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(A)

      go(`#/r/haifa/backlog/${B}`)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain(`Title ${A}`)
      expect(wrapper.find('[data-test="loading-id"]').text()).toBe(B)

      api.answer(B)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(B)
      expect(wrapper.find('[data-test="detail-loading"]').exists()).toBe(false)
      wrapper.unmount()
    })

    it('does not let a slow older answer overwrite the newer one', async () => {
      go(`#/r/haifa/backlog/${A}`)
      const api = slowFetch()
      const wrapper = mount(BacklogView)
      await flushPromises()
      go(`#/r/haifa/backlog/${B}`)
      await flushPromises()
      api.answer(B)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(B)
      api.answer(A)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(B)
      expect(wrapper.text()).not.toContain(`Title ${A}`)
      expect(wrapper.find('[data-test="refresh"]').attributes('disabled')).toBeUndefined()
      wrapper.unmount()
    })

    it('does not show a live refresh of the previous task in the new one', async () => {
      go(`#/r/haifa/backlog/${A}`)
      vi.stubGlobal('EventSource', FakeEventSource)
      const api = slowFetch()
      const wrapper = mount(BacklogView)
      api.answer(A)
      await flushPromises()
      FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, task_ids: [A] }))
      await debounce()
      await flushPromises()
      expect(api.pending[`/api/repos/haifa/backlog/tasks/${A}`]).toHaveLength(2)
      go(`#/r/haifa/backlog/${B}`)
      await flushPromises()
      api.answer(A, 1)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="loading-id"]').text()).toBe(B)
      api.answer(B)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(B)
      wrapper.unmount()
    })

    it('keeps the task shown while the same task reloads', async () => {
      go(`#/r/haifa/backlog/${A}`)
      const api = slowFetch()
      const wrapper = mount(BacklogView)
      api.answer(A)
      await flushPromises()
      await wrapper.find('[data-test="refresh"]').trigger('click')
      await flushPromises()
      expect(api.pending[`/api/repos/haifa/backlog/tasks/${A}`]).toHaveLength(2)
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(A)
      expect(wrapper.find('[data-test="detail-loading"]').exists()).toBe(false)
      api.answer(A, 1)
      await flushPromises()
      expect(wrapper.find('[data-test="task-id"]').text()).toBe(A)
      wrapper.unmount()
    })
  })

  it('keeps the tree folding across a task detail and back', async () => {
    go('#/r/haifa/backlog')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => ok(url.startsWith('/api/repos/haifa/backlog/tasks/') ? taskDetail() : backlogData())),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.findAll('a.task-link')).toHaveLength(0)
    await wrapper.find('[data-node="M01"] > .row [data-test="toggle"]').trigger('click')
    await wrapper.find('[data-node="M01-S01"] > .row [data-test="toggle"]').trigger('click')
    expect(wrapper.findAll('a.task-link')).toHaveLength(3)
    go('#/r/haifa/backlog/M01-S01-T02')
    await flushPromises()
    expect(wrapper.find('[data-test="tree"]').exists()).toBe(false)
    go('#/r/haifa/backlog')
    await flushPromises()
    expect(wrapper.findAll('a.task-link')).toHaveLength(3)
    expect(wrapper.find('[data-node="M02-S01"]').exists()).toBe(false)
    wrapper.unmount()
    // a fresh mount (another visit) reads the folding from the browser
    resetTreeForTests()
    const again = mount(BacklogView)
    await flushPromises()
    expect(again.findAll('a.task-link')).toHaveLength(3)
    again.unmount()
  })

  it('filters the kanban by project and step', async () => {
    go('#/r/haifa/backlog')
    const fetchMock = vi.fn(async (_url: string) => ok(backlogData()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="project-filter"]').exists()).toBe(false)
    await wrapper.find('[data-test="mode-kanban"]').trigger('click')
    const cards = () => wrapper.findAll('[data-card]').map((c) => c.attributes('data-card')).sort()
    expect(cards()).toEqual(['M01-S01-T01', 'M01-S01-T02', 'M01-S01-T03', 'M02-S01-T01'])
    expect(wrapper.find('[data-test="project-filter"]').element.parentElement?.textContent).toContain('Modul')
    expect(wrapper.find('[data-test="step-filter"]').element.parentElement?.textContent).toContain('Step')
    expect(await selectLabels(wrapper, '[data-test="step-filter"]')).toEqual(['vše', 'M01-S01 – Model', 'M02-S01 – UI'])
    const calls = fetchMock.mock.calls.length
    await chooseOption(wrapper, '[data-test="project-filter"]', 'M01')
    expect(fetchMock.mock.calls.length).toBe(calls)
    expect(cards()).toEqual(['M01-S01-T01', 'M01-S01-T02', 'M01-S01-T03'])
    expect(await selectLabels(wrapper, '[data-test="step-filter"]')).toEqual(['vše', 'M01-S01 – Model'])
    await chooseOption(wrapper, '[data-test="step-filter"]', 'M01-S01')
    expect(cards()).toEqual(['M01-S01-T01', 'M01-S01-T02', 'M01-S01-T03'])
    await chooseOption(wrapper, '[data-test="project-filter"]', 'M02')
    expect(cards()).toEqual(['M02-S01-T01'])
    // an empty filter means all
    await chooseOption(wrapper, '[data-test="project-filter"]', '')
    expect(cards()).toHaveLength(4)
    wrapper.unmount()
  })

  describe('Skrýt hotové', () => {
    /** The fixture plus project M03 whose only step has just done and cancelled tasks. */
    function withFinishedProject() {
      const data = backlogData()
      const done = taskNode({ id: 'M03-S01-T01', title: 'Old', path: 'backlog/M03/S01/a.md', board_state: 'done', status: 'done' })
      const cancelled = taskNode({ id: 'M03-S01-T02', title: 'Gone', path: 'backlog/M03/S01/b.md', board_state: 'cancelled', status: 'cancelled' })
      const step = { kind: 'container' as const, id: 'M03-S01', title: 'Old', level: 'step', path: 'backlog/M03/S01', progress: { done: 1, total: 2 }, done: true, blocks: [], children: [done, cancelled] }
      const project = { kind: 'container' as const, id: 'M03', title: 'Done', level: 'module', path: 'backlog/M03', progress: { done: 1, total: 2 }, done: true, blocks: [], children: [step] }
      return backlogData({ items: [...data.items, project], tasks: [...data.tasks, done, cancelled] })
    }

    it('hides done and cancelled tasks from the tree and the kanban and remembers it', async () => {
      go('#/r/haifa/backlog')
      expandTree(['M01', 'M01-S01', 'M02', 'M02-S01', 'M03', 'M03-S01'])
      vi.stubGlobal('fetch', vi.fn(async () => ok(withFinishedProject())))
      const wrapper = mount(BacklogView)
      await flushPromises()
      const box = () => wrapper.find<HTMLInputElement>('[data-test="hide-done"]')
      expect(box().element.checked).toBe(false)
      expect(wrapper.findAll('a.task-link')).toHaveLength(6)
      expect(wrapper.text()).toContain('M03')
      await box().setValue(true)
      expect(localStorage.getItem(HIDE_DONE_KEY)).toBe('1')
      const links = wrapper.findAll('a.task-link').map((a) => a.attributes('href'))
      expect(links).toEqual(['#/r/haifa/backlog/M01-S01-T02', '#/r/haifa/backlog/M01-S01-T03', '#/r/haifa/backlog/M02-S01-T01'])
      expect(wrapper.text()).not.toContain('M03')
      await wrapper.find('[data-test="mode-kanban"]').trigger('click')
      expect(wrapper.findAll('[data-column]').map((c) => c.attributes('data-column'))).toEqual([
        'todo',
        'ready',
        'deferred',
        'blocked',
        'running',
        'in review',
      ])
      expect(wrapper.find('[data-card="M01-S01-T01"]').exists()).toBe(false)
      wrapper.unmount()

      // the browser remembers the switch
      resetTreeForTests()
      const again = mount(BacklogView)
      await flushPromises()
      expect(again.find<HTMLInputElement>('[data-test="hide-done"]').element.checked).toBe(true)
      expect(again.text()).not.toContain('M03')
      await again.find<HTMLInputElement>('[data-test="hide-done"]').setValue(false)
      expect(localStorage.getItem(HIDE_DONE_KEY)).toBe('0')
      expect(again.text()).toContain('M03')
      again.unmount()
    })

    it('hides done tasks from the graph', async () => {
      localStorage.setItem(HIDE_DONE_KEY, '1')
      resetTreeForTests()
      go('#/r/haifa/backlog/graph/M01-S01')
      vi.stubGlobal(
        'fetch',
        vi.fn(async (url: string) => ok(url.endsWith('/graph') ? containerGraph() : backlogData())),
      )
      const wrapper = mount(BacklogView)
      await flushPromises()
      expect(wrapper.find('[data-node="M01-S01-T01"]').exists()).toBe(false)
      expect(wrapper.find('[data-node="M01-S01-T02"]').exists()).toBe(true)
      await wrapper.find<HTMLInputElement>('[data-test="hide-done"]').setValue(false)
      expect(wrapper.find('[data-node="M01-S01-T01"]').exists()).toBe(true)
      wrapper.unmount()
    })
  })

  it('shows the Bez workflow column only when some task has it', async () => {
    go('#/r/haifa/backlog')
    const data = backlogData()
    const noTodo = backlogData({ tasks: data.tasks.filter((t) => t.board_state !== 'todo') })
    let answer = noTodo
    vi.stubGlobal('fetch', vi.fn(async () => ok(answer)))
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="mode-kanban"]').trigger('click')
    expect(wrapper.find('[data-column="todo"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-column]')).toHaveLength(7)
    wrapper.unmount()

    answer = backlogData({ state_counts: { todo: 1, ready: 1 } })
    const shown = mount(BacklogView)
    await flushPromises()
    await shown.find('[data-test="mode-kanban"]').trigger('click')
    expect(shown.find('[data-column="todo"] h2').text()).toContain('Bez workflow')
    shown.unmount()
  })
})

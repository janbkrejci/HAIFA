// Spinners on Backlog actions: the clicked button spins until the server answers,
// colliding actions are disabled meanwhile, and a `pending` run start spins until live updates.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import BacklogView from './BacklogView.vue'
import {
  backlogData,
  runCheck,
  runStart,
  taskDetail,
  taskNode,
  taskRun,
} from '@/test/backlogFixtures'
import { deferred } from '@/test/deferred'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, traceEvent } from '@/test/fakeEventSource'

const TASK = 'M01-S01-T02'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function debounce() {
  return new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
}

function spinners(wrapper: VueWrapper) {
  return wrapper.findAll('[data-test="spinner"]')
}

function spins(wrapper: VueWrapper, selector: string): boolean {
  return wrapper.find(`${selector} [data-test="spinner"]`).exists()
}

function disabled(wrapper: VueWrapper, selector: string): boolean {
  return wrapper.find(selector).attributes('disabled') !== undefined
}

const written = () => ok({ action: 'edit', changed: true, path: 'x', task: taskNode(), issues: [] })

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/backlog')
})

describe('BacklogView spinners', () => {
  it('spins Spustit while the run is checked', async () => {
    go(`#/r/haifa/backlog/${TASK}`)
    const check = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/run-check')) return check.promise
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    expect(spins(wrapper, '[data-test="run"]')).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    expect(disabled(wrapper, '[data-test="run"]')).toBe(true)
    check.resolve(ok(runCheck()))
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })

  it('spins only the clicked run button, then opens the started run', async () => {
    go(`#/r/haifa/backlog/${TASK}`)
    const start = deferred<Response>()
    let started = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' && url.endsWith('/run')) return start.promise
        if (url.endsWith('/run-check')) {
          return ok(runCheck({ config: { base: 'main', commit: 'abc', clean: false, changes: [] } }))
        }
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) {
          return ok(started ? taskDetail({ runs: [...taskDetail().runs, taskRun()] }) : taskDetail())
        }
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="run-start"]').trigger('click')
    await flushPromises()
    expect(spins(wrapper, '[data-test="run-start"]')).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    expect(disabled(wrapper, '[data-test="run-start"]')).toBe(true)
    expect(disabled(wrapper, '[data-test="run-cancel"]')).toBe(true)
    started = true
    start.resolve(new Response(JSON.stringify({ ok: true, data: runStart(), error: null, warnings: [] }), { status: 202 }))
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    expect(window.location.hash).toBe('#/r/haifa/runs/r-9')
    wrapper.unmount()
  })

  it('spins Spustit přesto, not Spustit', async () => {
    go(`#/r/haifa/backlog/${TASK}`)
    const start = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' && url.endsWith('/run')) return start.promise
        if (url.endsWith('/run-check')) {
          return ok(runCheck({ unmet: [{ id: 'M01-S01-T01', reason: 'not_done', missing: ['M01-S01-T01'] }] }))
        }
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="run-force"]').trigger('click')
    await flushPromises()
    expect(spins(wrapper, '[data-test="run-force"]')).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    expect(disabled(wrapper, '[data-test="run-force"]')).toBe(true)
    start.resolve(ok(runStart({ force: true })))
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    expect(window.location.hash).toBe('#/r/haifa/runs/r-9')
    wrapper.unmount()
  })

  it('keeps spinning a pending start until the run shows up in live updates', async () => {
    go(`#/r/haifa/backlog/${TASK}`)
    vi.stubGlobal('EventSource', FakeEventSource)
    let launched = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' && url.endsWith('/run')) return ok(runStart({ run: null, pending: true }))
        if (url.endsWith('/run-check')) return ok(runCheck())
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) {
          return ok(launched ? taskDetail({ runs: [...taskDetail().runs, taskRun({ run_id: 'r-42' })] }) : taskDetail())
        }
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="run-start"]').trigger('click')
    await flushPromises()
    expect(spins(wrapper, '[data-test="run-start"]')).toBe(true)
    expect(disabled(wrapper, '[data-test="run-start"]')).toBe(true)
    const result = wrapper.find('[data-test="run-result"]')
    expect(result.text()).toContain('Běh se spouští')
    expect(result.text()).not.toContain('obnov')
    expect(result.find('a').exists()).toBe(false)

    launched = true
    FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, task_ids: [TASK] }))
    await debounce()
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    // a pending start stays on the task and offers to open the run once it shows up
    expect(wrapper.get('[data-test="run-result"]').text()).toContain('r-42')
    expect(wrapper.get('[data-test="run-open"]').attributes('href')).toBe('#/r/haifa/runs/r-42')
    expect(disabled(wrapper, '[data-test="run-start"]')).toBe(true)
    wrapper.unmount()
  })

  it('spins Commitnout backlog do base', async () => {
    go(`#/r/haifa/backlog/${TASK}`)
    const commit = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' && url === '/api/repos/haifa/backlog/commit') return commit.promise
        if (url.endsWith('/run-check')) return ok(runCheck({ in_base: false }))
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="run"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="commit-backlog"]').trigger('click')
    await flushPromises()
    expect(spins(wrapper, '[data-test="commit-backlog"]')).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    expect(disabled(wrapper, '[data-test="run-start"]')).toBe(true)
    commit.resolve(ok({ committed: true, commit: 'abc', base: 'main', paths: [], pushed: false }))
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })

  it.each([
    ['link-add', 'link-input'],
    ['related-add', 'related-input'],
    ['unlink-M01-S01-T01', null],
    ['unrelate-M02-S01-T01', null],
    ['assign', null],
  ])('spins only %s while the write runs', async (button, input) => {
    go(`#/r/haifa/backlog/${TASK}`)
    const gate = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' || init?.method === 'PATCH' || init?.method === 'PUT') {
          return gate.promise
        }
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    if (input) await wrapper.find(`[data-test="${input}"]`).setValue('M01-S01-T09')
    await wrapper.find(`[data-test="${button}"]`).trigger('click')
    await flushPromises()
    expect(spins(wrapper, `[data-test="${button}"]`)).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    for (const other of ['link-add', 'related-add', 'unlink-M01-S01-T01', 'unrelate-M02-S01-T01', 'assign', 'edit']) {
      expect(disabled(wrapper, `[data-test="${other}"]`)).toBe(true)
    }
    gate.resolve(written())
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    expect(disabled(wrapper, '[data-test="assign"]')).toBe(false)
    wrapper.unmount()
  })

  it('spins Uložit of the edit form', async () => {
    go(`#/r/haifa/backlog/${TASK}`)
    const gate = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method && init.method !== 'GET') return gate.promise
        if (url.startsWith('/api/repos/haifa/backlog/tasks/')) return ok(taskDetail())
        return ok(backlogData())
      }),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="edit"]').trigger('click')
    await wrapper.find('[data-test="title"]').setValue('Loader 2')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(spins(wrapper, '[data-test="save"]')).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    expect(disabled(wrapper, '[data-test="save"]')).toBe(true)
    expect(disabled(wrapper, '[data-test="link-add"]')).toBe(true)
    gate.resolve(written())
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })

  it('spins Založit of the new task form', async () => {
    go('#/r/haifa/backlog/new')
    const gate = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) =>
        init?.method === 'POST' ? gate.promise : ok(backlogData()),
      ),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.find('[data-test="title"]').setValue('Nový task')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(spins(wrapper, '[data-test="save"]')).toBe(true)
    expect(spinners(wrapper)).toHaveLength(1)
    expect(disabled(wrapper, '[data-test="save"]')).toBe(true)
    gate.resolve(ok({ action: 'add', changed: true, path: 'x', task: taskNode({ id: 'M01-S01-T05' }), issues: [] }))
    await flushPromises()
    expect(spinners(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })

  it('holds the kanban queue controls while the order is saved', async () => {
    go('#/r/haifa/backlog')
    const gate = deferred<Response>()
    const t4 = taskNode({ id: 'M01-S01-T04', path: 'backlog/M01-core/S01-model/M01-S01-T04-x.md' })
    const list = backlogData()
    list.tasks = [...list.tasks, t4]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => (init?.method === 'POST' ? gate.promise : ok(list))),
    )
    const wrapper = mount(BacklogView)
    await flushPromises()
    await wrapper.get('[data-test="mode-kanban"]').trigger('click')
    await wrapper.get('[data-item="M01-S01-T04"] [data-test="move-up"]').trigger('click')
    await flushPromises()
    expect(disabled(wrapper, '[data-item="M01-S01-T04"] [data-test="move-down"]')).toBe(true)
    expect(disabled(wrapper, '[data-item="M01-S01-T02"] [data-test="exclude-toggle"]')).toBe(true)
    gate.resolve(ok({ order: ['M01-S01-T04', 'M01-S01-T02'] }))
    await flushPromises()
    expect(disabled(wrapper, '[data-item="M01-S01-T02"] [data-test="exclude-toggle"]')).toBe(false)
    wrapper.unmount()
  })

  it('spins the refresh icon and shows no empty list before the first load', async () => {
    go('#/r/haifa/backlog')
    const list = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(async () => list.promise))
    const wrapper = mount(BacklogView)
    await flushPromises()
    expect(wrapper.find('[data-test="refresh"] svg').classes()).toContain('spin')
    expect(wrapper.find('[data-test="empty-tree"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="list-loading"]').exists()).toBe(true)
    list.resolve(ok(backlogData({ items: [] })))
    await flushPromises()
    expect(wrapper.find('[data-test="refresh"] svg').classes()).not.toContain('spin')
    expect(wrapper.find('[data-test="empty-tree"]').exists()).toBe(true)
    wrapper.unmount()
  })
})

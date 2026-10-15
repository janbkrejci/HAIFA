import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoControls from './RepoControls.vue'
import type { OverviewControl, OverviewRepo } from '@/lib/api'
import { factory, repo, running, tasks } from '@/test/overviewFixtures'
import { answerDialog } from '@/test/modal'

const api = vi.hoisted(() => ({
  controlStart: vi.fn(),
  controlPause: vi.fn(),
  controlResume: vi.fn(),
  controlStop: vi.fn(),
}))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }))

enableAutoUnmount(afterEach)

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
})

afterEach(() => {
  document.body.innerHTML = ''
})

function control(over: Partial<OverviewControl> = {}): OverviewControl {
  return {
    action: 'stop',
    run_ids: ['run-1', 'run-2'],
    pending: [],
    errors: [],
    started_at: '2026-10-06T10:00:00+00:00',
    finished_at: null,
    ...over,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

const TWO_RUNNING = [running({ run_id: 'run-1' }), running({ run_id: 'run-2', task_id: 'M01-S01-T02' })]

function mountWith(r: OverviewRepo) {
  return mount(RepoControls, { props: { repo: r }, attachTo: document.body })
}

describe('RepoControls', () => {
  it('shows Spustit továrnu only with a ready task and a free slot', () => {
    expect(mountWith(repo('a', { factory: factory({ can_start: false, ready: 2 }) })).find('[data-test="factory-start"]').exists()).toBe(false)
    expect(mountWith(repo('b', { factory: factory({ can_start: true, ready: 2 }) })).find('[data-test="factory-start"]').exists()).toBe(true)
    expect(mountWith(repo('c')).find('[data-test="factory-controls"]').exists()).toBe(false)
  })

  it('starts the factory with a spinner and emits changed after', async () => {
    const answer = deferred<unknown>()
    api.controlStart.mockReturnValue(answer.promise)
    const wrapper = mountWith(repo('a', { factory: factory({ can_start: true, ready: 3 }) }))
    await wrapper.find('[data-test="factory-start"]').trigger('click')
    expect(api.controlStart).toHaveBeenCalledWith('a')
    const button = wrapper.find('[data-test="factory-start"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')
    expect(wrapper.emitted('changed')).toBeUndefined()
    answer.resolve({
      max_parallel_runs: 2,
      running: 0,
      free_slots: 2,
      started: [{ task_id: 'T1', run_id: 'r1' }, { task_id: 'T2', run_id: null }],
      skipped: [],
    })
    await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[data-test="factory-start-message"]').text()).toBe('Spuštěno 2 běhy')
  })

  it('says why nothing started', async () => {
    api.controlStart.mockResolvedValue({
      max_parallel_runs: 2,
      running: 1,
      free_slots: 1,
      started: [],
      skipped: [{ task_id: 'T1', reason: 'writes_overlap', detail: 'běh r9 (T9): src/', waits_on: ['T9'] }],
    })
    const wrapper = mountWith(repo('a', { factory: factory({ can_start: true, ready: 1 }) }))
    await wrapper.find('[data-test="factory-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="factory-start-message"]').text()).toBe('Nic se nespustilo: T1 (běh r9 (T9): src/)')
  })

  it('offers Pauza, Pokračovat and Stop by the runs, none when nothing runs', () => {
    const idle = mountWith(repo('idle', { factory: factory({ ready: 0 }), tasks: tasks({ done: 1 }) }))
    for (const t of ['factory-pause', 'factory-resume', 'factory-stop']) expect(idle.find(`[data-test="${t}"]`).exists()).toBe(false)

    const busy = mountWith(repo('busy', { running: TWO_RUNNING }))
    expect(busy.find('[data-test="factory-pause"]').exists()).toBe(true)
    expect(busy.find('[data-test="factory-resume"]').exists()).toBe(false)
    expect(busy.find('[data-test="factory-stop"]').exists()).toBe(true)

    const paused = mountWith(repo('paused', { running: TWO_RUNNING.map((r) => ({ ...r, pause: 'paused' as const })) }))
    expect(paused.find('[data-test="factory-pause"]').exists()).toBe(false)
    expect(paused.find('[data-test="factory-resume"]').exists()).toBe(true)

    const ended = mountWith(repo('ended', { running: [running({ process: 'ended' })] }))
    expect(ended.find('[data-test="factory-stop"]').exists()).toBe(false)
  })

  it('pauses and resumes every run of the repo', async () => {
    api.controlPause.mockResolvedValue({ action: 'pause', run_ids: ['run-1'], errors: [] })
    api.controlResume.mockResolvedValue({ action: 'resume', run_ids: ['run-1'], errors: [] })
    const wrapper = mountWith(repo('a', { running: [running(), running({ run_id: 'run-2', pause: 'paused' })] }))
    await wrapper.find('[data-test="factory-pause"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="factory-resume"]').trigger('click')
    await flushPromises()
    expect(api.controlPause).toHaveBeenCalledWith('a')
    expect(api.controlResume).toHaveBeenCalledWith('a')
    expect(wrapper.emitted('changed')).toHaveLength(2)
  })

  it('asks before a stop and stops only when confirmed', async () => {
    api.controlStop.mockResolvedValue({ action: 'stop', run_ids: ['run-1', 'run-2'], pending: ['run-1', 'run-2'] })
    const wrapper = mountWith(repo('a', { running: TWO_RUNNING }))
    await wrapper.find('[data-test="factory-stop"]').trigger('click')
    await answerDialog(false)
    expect(api.controlStop).not.toHaveBeenCalled()
    await wrapper.find('[data-test="factory-stop"]').trigger('click')
    await answerDialog(true)
    expect(api.controlStop).toHaveBeenCalledWith('a')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('shows a request error', async () => {
    api.controlPause.mockRejectedValue(new Error('boom'))
    const wrapper = mountWith(repo('a', { running: TWO_RUNNING }))
    await wrapper.find('[data-test="factory-pause"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="factory-control-error"]').text()).toContain('boom')
  })

  it('shows the stop going on, then stopped, with the errors', () => {
    const stopping = mountWith(repo('a', { running: TWO_RUNNING, factory: factory({ control: control({ pending: ['run-1', 'run-2'] }) }) }))
    expect(stopping.find('[data-test="factory-control-status"]').text()).toBe('Zastavuje se – dobíhají 2 běhy')

    const stopped = mountWith(
      repo('b', {
        factory: factory({
          control: control({
            finished_at: '2026-10-06T10:01:00+00:00',
            errors: [{ run_id: 'run-2', task_id: 'T2', code: 'remote_run', message: 'jinde' }],
          }),
        }),
      }),
    )
    expect(stopped.find('[data-test="factory-control-status"]').text()).toBe('Zastaveno')
    expect(stopped.find('[data-test="factory-control-errors"]').text()).toBe('Nepodařilo se: T2 – jinde')
  })

  it('shows the pause going on, then paused', () => {
    const pause = factory({ control: control({ action: 'pause' }) })
    const going = mountWith(
      repo('a', { running: [running({ run_id: 'run-1', pause: 'paused' }), running({ run_id: 'run-2', pause: 'pausing' })], factory: pause }),
    )
    expect(going.find('[data-test="factory-control-status"]').text()).toBe('Pozastavuje se – dobíhá 1 běh')
    const done = mountWith(
      repo('b', { running: TWO_RUNNING.map((r) => ({ ...r, pause: 'paused' as const })), factory: pause }),
    )
    expect(done.find('[data-test="factory-control-status"]').text()).toBe('Pozastaveno')
  })

  it('shows the tasks per board state and the slots', () => {
    const wrapper = mountWith(
      repo('a', { tasks: tasks({ ready: 3, running: 1, done: 12 }), factory: factory({ running: 1, max_parallel_runs: 2 }) }),
    )
    const items = wrapper.findAll('[data-test="task-summary-item"]')
    expect(items.map((i) => i.attributes('data-state'))).toEqual(['ready', 'running', 'done'])
    expect(items.map((i) => i.text())).toEqual(['Připraveno 3', 'Běží 1', 'Hotovo 12'])
    expect(wrapper.find('[data-test="factory-slots"]').text()).toBe('Sloty: 1/2')
  })
})

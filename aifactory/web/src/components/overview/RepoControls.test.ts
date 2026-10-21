import { afterEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import RepoControls from './RepoControls.vue'
import type { OverviewControl, OverviewRepo } from '@/lib/api'
import { factory, repo, running, tasks } from '@/test/overviewFixtures'
import type { ControlFeedback } from './feedback'

enableAutoUnmount(afterEach)

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

const TWO_RUNNING = [running({ run_id: 'run-1' }), running({ run_id: 'run-2', task_id: 'M01-S01-T02' })]

function mountWith(r: OverviewRepo, feedback?: ControlFeedback) {
  return mount(RepoControls, { props: { repo: r, ...(feedback ? { feedback } : {}) } })
}

describe('RepoControls', () => {
  it('renders nothing without a state, a task or a message, and holds no buttons', () => {
    expect(mountWith(repo('c')).find('[data-test="factory-controls"]').exists()).toBe(false)
    const busy = mountWith(repo('busy', { running: TWO_RUNNING, tasks: tasks({ running: 2 }) }))
    expect(busy.find('[data-test="factory-controls"]').exists()).toBe(true)
    expect(busy.find('button').exists()).toBe(false)
  })

  it('shows the message and the error of the last button', () => {
    const ok = mountWith(repo('a'), { message: 'Spuštěno 2 běhy', error: null })
    expect(ok.get('[data-test="factory-start-message"]').text()).toBe('Spuštěno 2 běhy')
    expect(ok.find('[data-test="factory-control-error"]').exists()).toBe(false)
    const bad = mountWith(repo('a'), { message: null, error: 'boom' })
    expect(bad.get('[data-test="factory-control-error"]').text()).toBe('boom')
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
    expect(items.map((i) => i.attributes('data-state'))).toEqual(['running', 'ready', 'done'])
    expect(items.map((i) => i.text())).toEqual(['Běží 1', 'Připraveno 3', 'Hotovo 12'])
    // The same state classes colour the chips as in the backlog StateChip (style.css).
    expect(items.map((i) => i.classes())).toEqual([
      expect.arrayContaining(['state-chip', 'state-running']),
      expect.arrayContaining(['state-chip', 'state-ready']),
      expect.arrayContaining(['state-chip', 'state-done']),
    ])
    expect(wrapper.find('[data-test="factory-slots"]').text()).toBe('Sloty: 1/2')
  })

  it('counts the open PRs waiting for review among the slots', () => {
    const wrapper = mountWith(repo('a', { tasks: tasks({ ready: 1 }), factory: factory({ running: 1, in_review: 1, max_parallel_runs: 2 }) }))
    expect(wrapper.find('[data-test="factory-slots"]').text()).toBe('Sloty: 1/2 · v review 1')
  })
})

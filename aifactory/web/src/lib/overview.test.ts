import { describe, expect, it } from 'vitest'
import {
  canPause,
  canResume,
  canStart,
  canStop,
  controlStatus,
  countsById,
  failedRows,
  matchesFilter,
  problems,
  reviewLink,
  runLink,
  runsFinishing,
  sortRepos,
  stateClass,
  taskSummary,
  totals,
  urgency,
} from './overview'
import { fmtAge, fmtElapsed } from './format'
import type { OverviewFactory } from './api'
import { config, factory, failed, overview, repo, review, running, tasks } from '@/test/overviewFixtures'

const CALM = repo('calm')
const RUNS = repo('runs', { running: [running()] })
const REVIEW = repo('review', { review: [review()] })
const AUTOMERGE = repo('automerge', { automerge: [review({ task_id: 'M01-S01-T05' })] })
const FAILED = repo('failed', { failed: [failed()] })
const ENDED = repo('ended', { running: [running({ process: 'ended', status_label: 'proces skončil' })] })
const DIRTY = repo('dirty', { state: 'uncommitted', config: config({ uncommitted: [{ path: '.factory/x' }], clean: false }) })
const MISSING = repo('missing', { state: 'missing', config: null, has_trace: false, last_activity: null })

describe('overview urgency', () => {
  it('orders problems, failures, review, running, automerge, calm', () => {
    const order = sortRepos([CALM, AUTOMERGE, RUNS, REVIEW, FAILED, DIRTY]).map((r) => r.id)
    expect(order).toEqual(['dirty', 'failed', 'review', 'runs', 'automerge', 'calm'])
  })

  it('does not rank a repo that only waits for auto-merge as waiting for the user', () => {
    expect(urgency(AUTOMERGE)).toBe('automerge')
    expect(urgency(repo('both', { review: [review()], automerge: [review({ task_id: 'X' })] }))).toBe('review')
    // an older response without the list
    expect(urgency(repo('old', { automerge: undefined }))).toBe('calm')
  })

  it('orders repos of the same urgency by name', () => {
    expect(sortRepos([repo('b'), repo('a')]).map((r) => r.id)).toEqual(['a', 'b'])
  })

  it('counts a running row whose process ended as a failure', () => {
    expect(urgency(ENDED)).toBe('failed')
    expect(failedRows(ENDED)[0].label).toBe('proces skončil')
    expect(countsById(overview([ENDED])).ended).toEqual({ running: 0, review: 0, automerge: 0, failed: 1 })
  })

  it('labels a failed task with its failure kind, an older server with its error', () => {
    const rows = (f: Parameters<typeof failed>[0]) => failedRows(repo('f', { failed: [failed(f)] }))
    expect(rows({ failure_kind: 'quota' })[0].label).toBe('Vyčerpaná kvóta')
    expect(rows({ failure_kind: 'quota' })[0].error).toBe('tests failed')
    expect(rows({})[0].label).toBeNull()
  })

  it('treats warnings and a missing folder as problems', () => {
    expect(urgency(repo('w', { warnings: ['slow'] }))).toBe('problems')
    expect(urgency(MISSING)).toBe('problems')
    expect(problems(MISSING)).toEqual([{ kind: 'missing', text: 'Složka nenalezena', href: null }])
  })
})

describe('overview totals and filter', () => {
  const all = [CALM, RUNS, REVIEW, AUTOMERGE, FAILED, ENDED, DIRTY, MISSING]

  it('sums runs, review, auto-merge, failures and repos with problems', () => {
    expect(totals(all)).toEqual({ running: 1, review: 1, automerge: 1, failed: 2, problems: 2 })
  })

  it('filters the cards by a total', () => {
    expect(all.filter((r) => matchesFilter(r, 'running')).map((r) => r.id)).toEqual(['runs'])
    expect(all.filter((r) => matchesFilter(r, 'review')).map((r) => r.id)).toEqual(['review'])
    expect(all.filter((r) => matchesFilter(r, 'automerge')).map((r) => r.id)).toEqual(['automerge'])
    expect(all.filter((r) => matchesFilter(r, 'failed')).map((r) => r.id)).toEqual(['failed', 'ended'])
    expect(all.filter((r) => matchesFilter(r, 'problems')).map((r) => r.id)).toEqual(['dirty', 'missing'])
    expect(all.filter((r) => matchesFilter(r, null))).toHaveLength(all.length)
  })
})

describe('overview links', () => {
  it('leads to the run, the review and the Factory screen of the repo', () => {
    expect(runLink(RUNS, 'run-1')).toBe('#/r/runs/runs/run-1')
    expect(reviewLink(REVIEW, 'M01-S01-T02')).toBe('#/r/review/review/M01-S01-T02')
    const bad = repo('bad', { config: config({ installed: false, invalid: true, uncommitted: [{}] }) })
    expect(problems(bad).map((p) => [p.kind, p.text, p.href])).toEqual([
      ['not_installed', 'Nenainstalováno', '#/r/bad/factory'],
      ['invalid', 'Neplatná konfigurace', '#/r/bad/factory'],
      ['uncommitted', 'Necommitnutá konfigurace', '#/r/bad/factory/config_commit'],
    ])
  })
})

describe('overview formats', () => {
  it('formats elapsed time and age', () => {
    expect(fmtElapsed(45.7)).toBe('45s')
    expect(fmtElapsed(185)).toBe('3m 05s')
    expect(fmtElapsed(3720)).toBe('1h 02m')
    expect(fmtElapsed(null)).toBe('—')
    expect(fmtAge(10)).toBe('právě teď')
    expect(fmtAge(300)).toBe('před 5 min')
    expect(fmtAge(7200)).toBe('před 2 h')
    expect(fmtAge(2 * 86400)).toBe('před 2 d')
  })
})

describe('overview factory controls', () => {
  const stop = (over: Partial<NonNullable<OverviewFactory['control']>> = {}) =>
    factory({
      control: {
        action: 'stop',
        run_ids: [],
        pending: [],
        errors: [],
        started_at: '2026-10-06T10:00:00+00:00',
        finished_at: null,
        ...over,
      },
    })

  it('summarizes the tasks in kanban order without empty states', () => {
    expect(taskSummary(repo('a'))).toEqual([])
    expect(
      taskSummary(repo('a', { tasks: tasks({ done: 4, todo: 1, 'in review': 2, 'awaiting merge': 3 }) })),
    ).toEqual([
      { state: 'todo', label: 'Bez workflow', count: 1 },
      { state: 'in review', label: 'Čeká na review', count: 2 },
      { state: 'awaiting merge', label: 'Čeká na automerge PR', count: 3 },
      { state: 'done', label: 'Hotovo', count: 4 },
    ])
  })

  it('names the state chip colour class', () => {
    expect(stateClass('in review')).toBe('state-in-review')
    expect(stateClass('awaiting merge')).toBe('state-awaiting-merge')
    expect(stateClass('ready')).toBe('state-ready')
  })

  it('tells which controls apply', () => {
    expect(canStart(repo('a'))).toBe(false)
    expect(canStart(repo('a', { factory: factory({ can_start: true }) }))).toBe(true)
    const r = repo('a', { running: [running(), running({ run_id: 'r2', pause: 'pausing' })] })
    expect([canPause(r), canResume(r), canStop(r)]).toEqual([true, true, true])
    const ended = repo('a', { running: [running({ process: 'ended' })] })
    expect([canPause(ended), canResume(ended), canStop(ended)]).toEqual([false, false, false])
  })

  it('says how many runs are still finishing, in Czech plural', () => {
    expect(runsFinishing(1)).toBe('dobíhá 1 běh')
    expect(runsFinishing(3)).toBe('dobíhají 3 běhy')
    expect(runsFinishing(5)).toBe('dobíhá 5 běhů')
    expect(controlStatus(repo('a', { factory: stop({ pending: ['x', 'y', 'z', 'u', 'v'] }) }))).toEqual({
      kind: 'stopping',
      text: 'Zastavuje se – dobíhá 5 běhů',
    })
    expect(controlStatus(repo('a', { factory: stop({ finished_at: 'now' }) }))?.text).toBe('Zastaveno')
    expect(controlStatus(repo('a'))).toBeNull()
  })

  it('tells a pause going on from a pause in effect', () => {
    const pause = stop({ run_ids: ['run-1'] })
    pause.control!.action = 'pause'
    expect(controlStatus(repo('a', { running: [running({ pause: 'pausing' })], factory: pause }))?.text).toBe(
      'Pozastavuje se – dobíhá 1 běh',
    )
    expect(controlStatus(repo('a', { running: [running({ pause: 'paused' })], factory: pause }))).toEqual({
      kind: 'paused',
      text: 'Pozastaveno',
    })
    expect(controlStatus(repo('a', { factory: pause }))).toBeNull()
  })

  it('keeps a repo whose stop goes on out of the calm list', () => {
    expect(urgency(repo('a', { factory: stop({ pending: ['x'] }) }))).toBe('running')
    expect(urgency(repo('a', { factory: stop({ finished_at: 'now' }) }))).toBe('calm')
  })
})

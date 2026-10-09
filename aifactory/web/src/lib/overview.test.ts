import { describe, expect, it } from 'vitest'
import {
  countsById,
  failedRows,
  matchesFilter,
  problems,
  reviewLink,
  runLink,
  sortRepos,
  totals,
  urgency,
} from './overview'
import { fmtAge, fmtElapsed } from './format'
import { config, failed, overview, repo, review, running } from '@/test/overviewFixtures'

const CALM = repo('calm')
const RUNS = repo('runs', { running: [running()] })
const REVIEW = repo('review', { review: [review()] })
const FAILED = repo('failed', { failed: [failed()] })
const ENDED = repo('ended', { running: [running({ process: 'ended', status_label: 'proces skončil' })] })
const DIRTY = repo('dirty', { state: 'uncommitted', config: config({ uncommitted: [{ path: '.factory/x' }], clean: false }) })
const MISSING = repo('missing', { state: 'missing', config: null, has_trace: false, last_activity: null })

describe('overview urgency', () => {
  it('orders problems, failures, review, running, calm', () => {
    const order = sortRepos([CALM, RUNS, REVIEW, FAILED, DIRTY]).map((r) => r.id)
    expect(order).toEqual(['dirty', 'failed', 'review', 'runs', 'calm'])
  })

  it('orders repos of the same urgency by name', () => {
    expect(sortRepos([repo('b'), repo('a')]).map((r) => r.id)).toEqual(['a', 'b'])
  })

  it('counts a running row whose process ended as a failure', () => {
    expect(urgency(ENDED)).toBe('failed')
    expect(failedRows(ENDED)[0].label).toBe('proces skončil')
    expect(countsById(overview([ENDED])).ended).toEqual({ running: 0, review: 0, failed: 1 })
  })

  it('treats warnings and a missing folder as problems', () => {
    expect(urgency(repo('w', { warnings: ['slow'] }))).toBe('problems')
    expect(urgency(MISSING)).toBe('problems')
    expect(problems(MISSING)).toEqual([{ kind: 'missing', text: 'Složka nenalezena', href: null }])
  })
})

describe('overview totals and filter', () => {
  const all = [CALM, RUNS, REVIEW, FAILED, ENDED, DIRTY, MISSING]

  it('sums runs, review, failures and repos with problems', () => {
    expect(totals(all)).toEqual({ running: 1, review: 1, failed: 2, problems: 2 })
  })

  it('filters the cards by a total', () => {
    expect(all.filter((r) => matchesFilter(r, 'running')).map((r) => r.id)).toEqual(['runs'])
    expect(all.filter((r) => matchesFilter(r, 'review')).map((r) => r.id)).toEqual(['review'])
    expect(all.filter((r) => matchesFilter(r, 'failed')).map((r) => r.id)).toEqual(['failed', 'ended'])
    expect(all.filter((r) => matchesFilter(r, 'problems')).map((r) => r.id)).toEqual(['dirty', 'missing'])
    expect(all.filter((r) => matchesFilter(r, null))).toHaveLength(all.length)
  })
})

describe('overview links', () => {
  it('leads to the run, the review and the settings of the repo', () => {
    expect(runLink(RUNS, 'run-1')).toBe('#/r/runs/runs/run-1')
    expect(reviewLink(REVIEW, 'M01-S01-T02')).toBe('#/r/review/review/M01-S01-T02')
    const bad = repo('bad', { config: config({ installed: false, invalid: true, uncommitted: [{}] }) })
    expect(problems(bad).map((p) => [p.kind, p.text, p.href])).toEqual([
      ['not_installed', 'Nenainstalováno', '#/r/bad/settings'],
      ['invalid', 'Neplatná konfigurace', '#/r/bad/settings'],
      ['uncommitted', 'Necommitnutá konfigurace', '#/r/bad/settings'],
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

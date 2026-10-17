import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEMO_TASK, demoFinished, demoSteps, firstTestedHarness, lastStart, startDemo } from './demo'
import type { HarnessCatalog } from './machineHarnesses'
import type { PhaseDot, RunSummary } from './runs'

function envelope(data: unknown, ok = true) {
  return new Response(JSON.stringify(ok ? { ok, data, error: null, warnings: [] } : { ok, data: null, error: data, warnings: [] }))
}

function catalog(over: Partial<HarnessCatalog> = {}): HarnessCatalog {
  return {
    settings: {
      version: 1,
      default_harness: 'codex',
      harnesses: {
        claude: { enabled: true, model: 'claude-opus-5-5' },
        codex: { enabled: true, model: 'gpt-6.1-sol' },
        pi: { enabled: false, model: '' },
      },
    },
    available: { claude: true, codex: true, pi: false },
    models: {},
    configured: true,
    tests: {},
    ...over,
  }
}

const phase = (name: string, status = 'success'): PhaseDot => ({ seq: null, name, status })
const run = (state: RunSummary['state'], pr: RunSummary['pr'] = null) => ({ state, pr })

afterEach(() => {
  vi.unstubAllGlobals()
  lastStart.value = null
})

describe('firstTestedHarness', () => {
  it('takes the default harness when its model passed', () => {
    const tests = { claude: { 'claude-opus-5-5': { ok: true } }, codex: { 'gpt-6.1-sol': { ok: true } } }
    expect(firstTestedHarness(catalog({ tests }))).toEqual({ harness: 'codex', model: 'gpt-6.1-sol' })
  })

  it('skips a failed default and takes the next tested harness', () => {
    const tests = { claude: { 'claude-opus-5-5': { ok: true } }, codex: { 'gpt-6.1-sol': { ok: false } } }
    expect(firstTestedHarness(catalog({ tests }))).toEqual({ harness: 'claude', model: 'claude-opus-5-5' })
  })

  it('falls back to another tested model of an enabled harness', () => {
    const tests = { codex: { 'gpt-6.1-sol': { ok: false }, 'gpt-5.5': { ok: true } } }
    expect(firstTestedHarness(catalog({ tests }))).toEqual({ harness: 'codex', model: 'gpt-5.5' })
  })

  it('ignores disabled or missing harnesses and gives null without a passed test', () => {
    const tests = { pi: { 'openai/gpt': { ok: true } } }
    expect(firstTestedHarness(catalog({ tests }))).toBeNull()
    expect(firstTestedHarness(catalog())).toBeNull()
    expect(firstTestedHarness(null)).toBeNull()
  })
})

describe('startDemo', () => {
  it('creates the sample and runs its first task with the tested harness', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url === '/api/demo') return envelope({ path: '/h/demo', created: true, registered: true, repo_id: 'demo', base: 'main', provider: 'local' })
      if (url === '/api/machine/harnesses') return envelope(catalog({ tests: { claude: { 'claude-opus-5-5': { ok: true } } } }))
      if (url === `/api/repos/demo/backlog/tasks/${DEMO_TASK}/run`) return envelope({ task_id: DEMO_TASK, run: { run_id: 'r1' }, pending: false })
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await startDemo()

    expect(result).toEqual({ repoId: 'demo', harness: { harness: 'claude', model: 'claude-opus-5-5' }, runId: 'r1', error: null })
    expect(lastStart.value).toEqual(result)
    const runCall = fetchMock.mock.calls.find(([url]) => url.endsWith('/run'))
    expect(JSON.parse(String(runCall?.[1]?.body))).toEqual({ harness: 'claude', model: 'claude-opus-5-5' })
  })

  it('keeps the sample when the run does not start and reports why', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/demo') return envelope({ path: '/h/demo', created: false, registered: true, repo_id: 'demo', base: 'main', provider: 'local' })
      if (url === '/api/machine/harnesses') return new Response('nope', { status: 500 })
      return envelope({ code: 'task_busy', message: 'already running' }, false)
    }))

    const result = await startDemo()

    expect(result).toMatchObject({ repoId: 'demo', harness: null, runId: null, error: 'already running' })
  })
})

describe('demoSteps', () => {
  const states = (steps: ReturnType<typeof demoSteps>) => steps.map((s) => `${s.id}:${s.state}`)

  it('follows the running run phase by phase', () => {
    expect(states(demoSteps(run('running'), []))).toEqual(['worktree:current', 'build:todo', 'test:todo', 'review:todo', 'pr:todo', 'merge:todo'])
    expect(states(demoSteps(run('running'), [phase('build', 'running')]))[1]).toBe('build:current')
    const tested = demoSteps(run('running'), [phase('build'), phase('test_plan'), phase('test_1')])
    expect(states(tested)).toEqual(['worktree:done', 'build:done', 'test:done', 'review:current', 'pr:todo', 'merge:todo'])
    expect(tested.find((s) => s.state === 'current')?.text).toMatch(/zeleného kódu/)
  })

  it('a red test is not done; the fix counts as build', () => {
    const steps = demoSteps(run('running'), [phase('build', 'failed'), phase('test_1', 'failed'), phase('fix_1')])
    expect(states(steps).slice(1, 3)).toEqual(['build:done', 'test:current'])
  })

  it('waits for the merge of the open PR, then everything is done', () => {
    const open = { url: '', pr_id: '1', state: 'open' }
    expect(states(demoSteps(run('succeeded', open), [phase('build')])).slice(3)).toEqual(['review:done', 'pr:done', 'merge:current'])
    const merged = { ...open, state: 'merged' }
    expect(demoSteps(run('succeeded', merged), []).every((s) => s.state === 'done')).toBe(true)
    expect(demoFinished(run('succeeded', merged))).toBe(true)
    expect(demoFinished(run('succeeded', open))).toBe(false)
  })

  it('a failed run has no current step', () => {
    expect(demoSteps(run('failed'), [phase('build')]).some((s) => s.state === 'current')).toBe(false)
  })
})

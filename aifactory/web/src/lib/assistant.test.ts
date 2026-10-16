import { describe, expect, it } from 'vitest'
import {
  actionOutcome,
  actionPreview,
  actionRequest,
  actionTitle,
  contextLabel,
  describeScreen,
  linkify,
  outcomeText,
  suggestions,
  type ProposedAction,
} from './assistant'

describe('describeScreen', () => {
  it('reads the run, the task and the PR of a repo screen', () => {
    expect(describeScreen('repo', 'haifa', 'runs', ['abc12345', 'p1'])).toEqual({
      kind: 'run',
      context: { repo: 'haifa', run: 'abc12345' },
    })
    expect(describeScreen('repo', 'haifa', 'backlog', ['P01-S01-T01'])).toEqual({
      kind: 'task',
      context: { repo: 'haifa', task: 'P01-S01-T01' },
    })
    expect(describeScreen('repo', 'haifa', 'review', ['P01-S01-T01']).kind).toBe('pr')
    expect(describeScreen('repo', 'haifa', 'backlog', ['new', 'P01-S01'])).toEqual({
      kind: 'backlog',
      context: { repo: 'haifa' },
    })
    expect(describeScreen('repo', 'haifa', 'factory', ['settings']).context).toEqual({ repo: 'haifa' })
  })

  it('has no context off a repo page', () => {
    expect(describeScreen('overview', null, 'backlog', [])).toEqual({ kind: 'overview', context: null })
    expect(describeScreen('guide', null, 'backlog', ['uvod']).kind).toBe('other')
  })

  it('labels the context chip', () => {
    expect(contextLabel({ repo: 'haifa', run: 'abc12345' })).toBe('repo haifa · běh abc12345')
  })
})

describe('suggestions', () => {
  it('asks why a failed run failed', () => {
    const offered = suggestions('run', 'failed')
    expect(offered).toHaveLength(3)
    expect(offered[0]).toBe('Proč tenhle běh selhal?')
    expect(suggestions('run', 'succeeded')).not.toContain('Proč tenhle běh selhal?')
  })

  it('offers three questions on every screen', () => {
    for (const kind of ['task', 'pr', 'backlog', 'runs', 'review', 'factory', 'overview', 'setup', 'other'] as const) {
      expect(suggestions(kind)).toHaveLength(3)
    }
  })
})

describe('linkify', () => {
  it('links tasks, runs and PRs into the dashboard', () => {
    const out = linkify('Task P01-S01-T02 selhal v běhu 740183f7, viz PR #12.', 'haifa')
    expect(out).toContain('[P01-S01-T02](#/r/haifa/backlog/P01-S01-T02)')
    expect(out).toContain('[740183f7](#/r/haifa/runs/740183f7)')
    expect(out).toContain('[PR #12](#/r/haifa/review)')
  })

  it('links an id in inline code', () => {
    expect(linkify('Task `GUIDE-S02-T02` a běh `740183f7`', 'haifa')).toBe(
      'Task [GUIDE-S02-T02](#/r/haifa/backlog/GUIDE-S02-T02) a běh [740183f7](#/r/haifa/runs/740183f7)',
    )
  })

  it('keeps fenced code, existing links and other hex alone', () => {
    const source = [
      '[P01-S01-T01](#/r/other/backlog/P01-S01-T01)',
      'commit 740183f7',
      '```',
      'P01-S01-T03',
      '```',
    ].join('\n')
    expect(linkify(source, 'haifa')).toBe(source)
  })

  it('changes nothing without a repository', () => {
    expect(linkify('P01-S01-T01', null)).toBe('P01-S01-T01')
  })
})

describe('proposed actions', () => {
  const edit: ProposedAction = {
    id: 'a1',
    kind: 'edit_task',
    repo: 'haifa',
    task: 'P01-S01-T01',
    writes: ['src/', 'docs/'],
    status: 'proposed',
  }

  it('maps every kind to the dashboard write API of the manual action', () => {
    expect(actionRequest(edit)).toEqual({
      path: '/repos/haifa/backlog/tasks/P01-S01-T01/edit',
      body: { writes: ['src/', 'docs/'] },
    })
    const base = { id: 'x', repo: 'haifa', status: 'proposed' as const }
    expect(actionRequest({ ...base, kind: 'cancel_task', task: 'T1' })).toEqual({
      path: '/repos/haifa/backlog/tasks/T1/edit',
      body: { status: 'cancelled' },
    })
    expect(actionRequest({ ...base, kind: 'run_task', task: 'T1', note: 'n' }).path).toBe('/repos/haifa/backlog/tasks/T1/run')
    expect(actionRequest({ ...base, kind: 'retry_run', run: 'abcd1234' }).path).toBe('/repos/haifa/runs/abcd1234/retry')
    expect(actionRequest({ ...base, kind: 'approve_pr', task: 'T1' })).toEqual({ path: '/repos/haifa/review/T1/approve' })
    expect(actionRequest({ ...base, kind: 'create_task', step: 'P01-S01', title: 'Nový' })).toEqual({
      path: '/repos/haifa/backlog/tasks',
      body: { step: 'P01-S01', title: 'Nový' },
    })
  })

  it('previews an edit against the current task', () => {
    const now = { title: 'First', body: 'Body', writes: ['src/'], workflow: null, status: 'todo' }
    expect(actionTitle(edit)).toBe('Upravit task P01-S01-T01')
    expect(actionPreview(edit, now)).toContainEqual({ label: 'Writes', before: 'src/', after: 'src/, docs/' })
    expect(actionPreview(edit)).toContainEqual({ label: 'Writes', before: null, after: 'src/, docs/' })
  })

  it('words the outcome', () => {
    expect(actionOutcome(edit, { changed: true })).toBe('Task upraven.')
    const run = { ...edit, kind: 'run_task' as const }
    expect(actionOutcome(run, { run: { run_id: 'abcd1234' } })).toBe('Běh abcd1234 spuštěn.')
    const done = { ...edit, status: 'done' as const, outcome: { message: 'Task upraven.', at: '' } }
    const messages = [{ id: 'm', role: 'assistant' as const, text: '', actions: [done] }]
    const note = { id: 'n', role: 'action' as const, text: 'raw', action_id: 'a1', status: 'done' as const }
    expect(outcomeText(note, messages)).toBe('Upravit task P01-S01-T01: provedeno — Task upraven.')
  })
})

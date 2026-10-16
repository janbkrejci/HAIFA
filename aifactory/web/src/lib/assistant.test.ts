import { describe, expect, it } from 'vitest'
import { contextLabel, describeScreen, linkify, suggestions } from './assistant'

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

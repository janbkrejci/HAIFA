// The kanban queue (order, Odloženo), the run payload, the test command field and the
// codes of new containers (lib/backlog.ts), the Czech PR states (lib/runs.ts) and the
// new task link with its step (lib/router.ts).
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  BOARD_STATES,
  childContainerIds,
  formatTestField,
  kanbanColumn,
  kanbanColumns,
  mergeQueueOrder,
  parseTestField,
  setAutoExcluded,
  setQueueOrder,
  splitShell,
  startRun,
  suggestContainerCode,
} from './backlog'
import { prStateLabel } from './runs'
import { newTaskHref } from './router'
import { backlogData, taskNode } from '@/test/backlogFixtures'

function stubFetch() {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
    new Response(JSON.stringify({ ok: true, data: {}, error: null, warnings: [] })),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = '#/r/haifa/backlog'
})

describe('kanban queue', () => {
  it('puts an excluded task that has not started into Odloženo', () => {
    expect(kanbanColumn(taskNode({ auto_excluded: true }))).toBe('deferred')
    expect(kanbanColumn(taskNode({ board_state: 'blocked', auto_excluded: true }))).toBe('deferred')
    expect(kanbanColumn(taskNode({ board_state: 'todo', auto_excluded: true }))).toBe('deferred')
    expect(kanbanColumn(taskNode({ board_state: 'running', auto_excluded: true }))).toBe('running')
    expect(kanbanColumn(taskNode({ board_state: 'in review', auto_excluded: true }))).toBe('in review')
    expect(kanbanColumn(taskNode({ board_state: 'done', auto_excluded: true }))).toBe('done')
    expect(kanbanColumn(taskNode())).toBe('ready')
  })

  it('shows Odloženo right after Připraveno, or last without it', () => {
    expect(kanbanColumns(BOARD_STATES).slice(0, 3)).toEqual(['todo', 'ready', 'deferred'])
    expect(kanbanColumns(['blocked', 'done'])).toEqual(['blocked', 'done', 'deferred'])
  })

  it('merges a reordered filtered column into the whole queue', () => {
    expect(mergeQueueOrder(['A', 'B', 'C', 'D'], ['D', 'B'])).toEqual(['A', 'D', 'C', 'B'])
    expect(mergeQueueOrder(['A', 'B', 'C'], ['C', 'A', 'B'])).toEqual(['C', 'A', 'B'])
    expect(mergeQueueOrder(['A', 'B'], ['X', 'B', 'A'])).toEqual(['B', 'A'])
  })

  it('posts the order and the exclusion to the repo API', async () => {
    window.location.hash = '#/r/haifa/backlog'
    const fetchMock = stubFetch()
    await setQueueOrder(['M01-S01-T02', 'M01-S01-T03'])
    await setAutoExcluded('M01-S01-T02', true)
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method, init?.body])).toEqual([
      ['/api/repos/haifa/backlog/queue/order', 'POST', '{"order":["M01-S01-T02","M01-S01-T03"]}'],
      ['/api/repos/haifa/backlog/tasks/M01-S01-T02/auto-exclude', 'POST', '{"excluded":true}'],
    ])
  })

  it('sends the harness of a run and auto continue', async () => {
    const fetchMock = stubFetch()
    await startRun('M01-S01-T02', { force: false, harness: 'codex', model: 'gpt-5', thinking: 'high', auto: true })
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      force: false, harness: 'codex', model: 'gpt-5', thinking: 'high', auto: true,
    })
  })
})

describe('test command field', () => {
  it('splits like a shell and joins back like shlex', () => {
    expect(splitShell(`pytest -k "a b" 'c d' e\\ f`)).toEqual(['pytest', '-k', 'a b', 'c d', 'e f'])
    expect(splitShell('  ')).toEqual([])
    expect(splitShell(`echo ""`)).toEqual(['echo', ''])
    expect(formatTestField(['pytest', '-k', 'a b', "it's"])).toBe(`pytest -k 'a b' 'it'"'"'s'`)
    expect(formatTestField('just check')).toBe('just check')
    expect(formatTestField(null)).toBe('')
  })

  it('reads one command as argv, empty as inherited', () => {
    expect(parseTestField(' just  check ')).toEqual(['just', 'check'])
    expect(parseTestField('just\ncheck')).toEqual(['just', 'check'])
    expect(parseTestField('')).toBeNull()
    for (const argv of [['just', 'test'], ['pytest', '-k', 'a b'], ['sh', '-c', `echo "x'y"`]]) {
      expect(parseTestField(formatTestField(argv))).toEqual(argv)
    }
  })
})

describe('codes of new containers', () => {
  it('lists the containers under a parent or at the top', () => {
    const items = backlogData().items
    expect(childContainerIds(items, null)).toEqual(['M01', 'M02'])
    expect(childContainerIds(items, 'M01')).toEqual(['M01-S01'])
    expect(childContainerIds(items, 'M01-S01')).toEqual([])
    expect(childContainerIds(items, 'NOPE')).toEqual([])
  })

  it('suggests the next code', () => {
    expect(suggestContainerCode('project', null, [])).toBe('P01')
    expect(suggestContainerCode('module', null, ['M01', 'M02'])).toBe('M03')
    expect(suggestContainerCode('step', 'M01', ['M01-S01', 'M01-S09'])).toBe('M01-S10')
    expect(suggestContainerCode('step', 'HAIFA', [])).toBe('HAIFA-S01')
  })
})

describe('PR states and links', () => {
  it('names PR states in Czech', () => {
    expect(prStateLabel('open')).toBe('otevřený')
    expect(prStateLabel('merged')).toBe('sloučený')
    expect(prStateLabel('closed')).toBe('zavřený')
    expect(prStateLabel('weird')).toBe('weird')
    expect(prStateLabel(null)).toBe('—')
  })

  it('links the new task form with its step', () => {
    window.location.hash = '#/r/haifa/backlog'
    expect(newTaskHref()).toBe('#/r/haifa/backlog/new')
    expect(newTaskHref('M01-S01')).toBe('#/r/haifa/backlog/new/M01-S01')
  })
})

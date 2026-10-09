import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import {
  linkActionKey,
  newRun,
  addTask,
  autoMode,
  commitBacklog,
  editTask,
  fetchBacklog,
  fetchGraph,
  fetchRunCheck,
  fetchTask,
  flattenIssues,
  linkTask,
  setAutoContinue,
  setAutoMerge,
  startRun,
  splitIds,
  splitLines,
  HIDE_DONE_KEY,
  STATE_LABELS,
  graphWithoutDone,
  hideDone,
  presentStates,
  pruneDone,
  resetHideDoneForTests,
  setHideDone,
  stateCounts,
  type BacklogNode,
} from './backlog'
import { backlogData, containerGraph, taskNode } from '@/test/backlogFixtures'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function stubFetch(response: () => Response) {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('backlog api', () => {
  it('asks for the whole backlog', async () => {
    const fetchMock = stubFetch(() => ok({ items: [] }))
    await fetchBacklog()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/backlog')
  })

  it('encodes task ids', async () => {
    const fetchMock = stubFetch(() => ok({}))
    await fetchTask('a/b')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/backlog/tasks/a%2Fb')
  })

  it('posts writes as JSON', async () => {
    const fetchMock = stubFetch(() => ok({ action: 'add' }))
    await addTask({ step: 'M01-S01', title: 'Nový' })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/backlog/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"step":"M01-S01","title":"Nový"}',
    })
    await editTask('T1', { clear_workflow: true })
    expect(fetchMock.mock.lastCall?.[0]).toBe('/api/repos/haifa/backlog/tasks/T1/edit')
    await linkTask('T1', { depends_on: ['T0'], remove: true })
    expect(fetchMock.mock.lastCall?.[0]).toBe('/api/repos/haifa/backlog/tasks/T1/link')
    expect(fetchMock.mock.lastCall?.[1]?.body).toBe('{"depends_on":["T0"],"remove":true}')
  })

  it('throws ApiError with the validation issues', async () => {
    const issue = { code: 'cycle', message: 'cycle T1 -> T1', path: 'backlog/t.md', id: 'T1' }
    stubFetch(
      () =>
        new Response(
          JSON.stringify({
            ok: false,
            data: null,
            error: { code: 'backlog_invalid', message: 'rejected', path: null, id: null, issues: [issue] },
            warnings: [],
          }),
          { status: 422 },
        ),
    )
    const error = await linkTask('T1', { depends_on: ['T3'] }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(flattenIssues(error)).toEqual({ message: 'rejected', issues: [issue], code: 'backlog_invalid' })
    expect(flattenIssues(new Error('boom'))).toEqual({ message: 'boom', issues: [] })
  })

  it('calls the run, graph and auto-continue endpoints', async () => {
    const fetchMock = stubFetch(() => ok({}))
    await fetchRunCheck('T1')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/backlog/tasks/T1/run-check')
    await startRun('T1', { note: 'z UI', force: true })
    expect(fetchMock.mock.lastCall?.[0]).toBe('/api/repos/haifa/backlog/tasks/T1/run')
    expect(fetchMock.mock.lastCall?.[1]?.body).toBe('{"note":"z UI","force":true}')
    await fetchGraph('M01/S01')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/backlog/containers/M01%2FS01/graph')
    await setAutoContinue('M01', 'inherit')
    expect(fetchMock.mock.lastCall?.[0]).toBe('/api/repos/haifa/backlog/containers/M01/auto-continue')
    expect(fetchMock.mock.lastCall?.[1]?.body).toBe('{"mode":"inherit"}')
    await setAutoMerge('M01', 'on')
    expect(fetchMock.mock.lastCall?.[0]).toBe('/api/repos/haifa/backlog/containers/M01/auto-merge')
    expect(fetchMock.mock.lastCall?.[1]?.body).toBe('{"mode":"on"}')
  })

  it('commits the backlog to base', async () => {
    const fetchMock = stubFetch(() => ok({ committed: true }))
    await commitBacklog()
    expect(fetchMock.mock.lastCall?.[0]).toBe('/api/repos/haifa/backlog/commit')
    expect(fetchMock.mock.lastCall?.[1]?.method).toBe('POST')
    expect(fetchMock.mock.lastCall?.[1]?.body).toBe('{}')
    await commitBacklog('backlog: nové tasky')
    expect(fetchMock.mock.lastCall?.[1]?.body).toBe('{"message":"backlog: nové tasky"}')
  })

  it('maps auto_continue to a switch position', () => {
    expect(autoMode(true)).toBe('on')
    expect(autoMode(false)).toBe('off')
    expect(autoMode(null)).toBe('inherit')
    expect(autoMode(undefined)).toBe('inherit')
  })

  it('splits ids and lines', () => {
    expect(splitIds(' A, B  C,,')).toEqual(['A', 'B', 'C'])
    expect(splitLines('src/\n\n  web/ \n')).toEqual(['src/', 'web/'])
  })
})

describe('linkActionKey', () => {
  it('names the clicked link button', () => {
    expect(linkActionKey({ depends_on: ['A'] })).toBe('link:depends_on')
    expect(linkActionKey({ related: ['A', 'B'] })).toBe('link:related')
    expect(linkActionKey({ depends_on: ['A'], remove: true })).toBe('unlink:depends_on:A')
    expect(linkActionKey({ related: ['R'], remove: true })).toBe('unlink:related:R')
  })
})

describe('newRun', () => {
  it('finds the run that started after the click, a running one first', () => {
    const known = new Set(['r-1'])
    expect(newRun([{ run_id: 'r-1' }], known)).toBeNull()
    expect(newRun(null, known)).toBeNull()
    expect(newRun([{ run_id: 'r-1' }, { run_id: 'r-2' }], known)?.run_id).toBe('r-2')
    expect(
      newRun(
        [
          { run_id: 'r-3', state: 'failed' },
          { run_id: 'r-4', state: 'running' },
        ],
        known,
      )?.run_id,
    ).toBe('r-4')
  })
})

describe('kanban filter by project and step', () => {
  it('returns the tasks of the project and step', async () => {
    const { backlogData } = await import('@/test/backlogFixtures')
    const { filterKanban } = await import('./backlog')
    const data = backlogData()
    const ids = (f: Parameters<typeof filterKanban>[2]) => filterKanban(data.tasks, data.items, f).map((t) => t.id)
    expect(ids({})).toEqual(['M01-S01-T01', 'M01-S01-T02', 'M01-S01-T03', 'M02-S01-T01'])
    expect(ids({ project: 'M01' })).toEqual(['M01-S01-T01', 'M01-S01-T02', 'M01-S01-T03'])
    expect(ids({ step: 'M02-S01' })).toEqual(['M02-S01-T01'])
    expect(ids({ project: 'M01', step: 'M02-S01' })).toEqual([])
  })

  it('offers projects and the steps of the chosen project', async () => {
    const { backlogData } = await import('@/test/backlogFixtures')
    const { projectOptions, stepOptions } = await import('./backlog')
    const data = backlogData()
    expect(projectOptions(data.items, data.steps)).toEqual([
      { id: 'M01', title: 'Core' },
      { id: 'M02', title: 'Web' },
    ])
    // a filtered tree misses a project: its title comes from the names
    expect(projectOptions([], data.steps, { M02: { title: 'Web', level: 'module' } })).toEqual([
      { id: 'M01', title: null },
      { id: 'M02', title: 'Web' },
    ])
    expect(stepOptions(data.steps, 'M02')).toEqual([{ id: 'M02-S01', title: 'UI' }])
    expect(stepOptions(data.steps).map((s) => s.id)).toEqual(['M01-S01', 'M02-S01'])
    // two levels: the steps are the projects
    const top = [{ id: 'A', title: 'Area', path: 'a', project: null }]
    expect(projectOptions([], top)).toEqual([{ id: 'A', title: 'Area' }])
    expect(stepOptions(top)).toEqual([])
  })
})

describe('Skrýt hotové', () => {
  afterEach(() => {
    localStorage.clear()
    resetHideDoneForTests()
  })

  it('is off by default and the browser remembers the choice', () => {
    localStorage.clear()
    resetHideDoneForTests()
    expect(hideDone()).toBe(false)
    setHideDone(true)
    expect(localStorage.getItem(HIDE_DONE_KEY)).toBe('1')
    resetHideDoneForTests()
    expect(hideDone()).toBe(true)
    setHideDone(false)
    resetHideDoneForTests()
    expect(hideDone()).toBe(false)
  })

  it('prunes done and cancelled tasks and the containers left without a task', () => {
    const items = backlogData().items
    // M01-S01 keeps the ready and blocked tasks
    const ids = (nodes: BacklogNode[]): string[] =>
      nodes.flatMap((n) => [n.id ?? '', ...(n.kind === 'container' ? ids(n.children) : [])])
    expect(ids(pruneDone(items))).toEqual(['M01', 'M01-S01', 'M01-S01-T02', 'M01-S01-T03', 'M02', 'M02-S01', 'M02-S01-T01'])
    const finished = backlogData({
      items: [
        ...items,
        {
          kind: 'container',
          id: 'M03',
          title: 'Done',
          level: 'module',
          path: 'backlog/M03',
          progress: { done: 1, total: 2 },
          done: true,
          blocks: [],
          children: [
            {
              kind: 'container',
              id: 'M03-S01',
              title: 'Old',
              level: 'step',
              path: 'backlog/M03/S01',
              progress: { done: 1, total: 2 },
              done: true,
              blocks: [],
              children: [
                taskNode({ id: 'M03-S01-T01', path: 'a.md', board_state: 'done' }),
                taskNode({ id: 'M03-S01-T02', path: 'b.md', board_state: 'cancelled' }),
              ],
            },
          ],
        },
      ],
    }).items
    expect(ids(pruneDone(finished))).not.toContain('M03')
    expect(ids(pruneDone(finished))).not.toContain('M03-S01')
    // the input is not changed
    expect(ids(finished)).toContain('M03-S01-T01')
  })

  it('drops done tasks and their arrows from the graph', () => {
    const graph = graphWithoutDone(containerGraph())
    expect(graph.nodes.map((n) => n.id)).toEqual(['M01-S01-T02', 'M01-S01-T03', 'M02'])
    expect(graph.edges).toEqual([
      { from: 'M01-S01-T02', to: 'M01-S01-T03' },
      { from: 'M02', to: 'M01-S01-T03' },
    ])
  })
})

describe('Bez workflow', () => {
  it('is the label of the todo state', () => {
    expect(STATE_LABELS.todo).toBe('Bez workflow')
  })

  it('shows the state only when some task has it', () => {
    const states = ['todo', 'ready', 'done'] as const
    expect(presentStates(states, { todo: 0, ready: 0 })).toEqual(['ready', 'done'])
    expect(presentStates(states, { todo: 1 })).toEqual(['todo', 'ready', 'done'])
  })

  it('counts the states from state_counts, else from the tasks', () => {
    expect(stateCounts(backlogData({ state_counts: { todo: 5 } }))).toEqual({ todo: 5 })
    expect(stateCounts(backlogData())).toEqual({ done: 1, ready: 1, blocked: 1, todo: 1 })
  })
})

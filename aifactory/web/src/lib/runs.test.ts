import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  applyTail,
  checksLabel,
  cursorsOf,
  excerpt,
  fetchPhasePrompts,
  archiveFinishedRuns,
  archiveRun,
  deleteArchivedRuns,
  deleteRun,
  fetchRuns,
  isFinished,
  shownState,
  slotWaitLabel,
  unarchiveRun,
  type RunTail,
} from './runs'
import { detail, events, summary } from '@/test/runsFixtures'

function tail(over: Partial<RunTail> = {}): RunTail {
  const base = detail()
  return {
    run: base.run,
    session: null,
    events: [],
    phases: [],
    gates: [],
    envelopes: [],
    agents: [],
    usage_delta: { read: 0, written: 0 },
    cursors: { events: 3, phases: 2, gates: 2, envelopes: 1 },
    has_more: false,
    ...over,
  }
}

describe('applyTail', () => {
  it('replaces phases by id, adds new ones and keeps them sorted by seq', () => {
    const current = detail()
    const [p2, p1] = current.phases
    const merged = applyTail(
      current,
      events(),
      tail({
        phases: [
          { ...p2, status: 'success' },
          { ...p1, phase_id: 'p3', seq: 3, name: 'review', status: 'running' },
        ],
      }),
    )
    expect(merged.detail.phases.map((p) => [p.phase_id, p.status])).toEqual([
      ['p1', 'success'],
      ['p2', 'success'],
      ['p3', 'running'],
    ])
  })

  it('appends events, gates and envelopes without duplicates and adds usage', () => {
    const current = detail()
    const evts = events()
    const [first] = evts
    const newEvent = { ...first, rowid: 4, event_id: 'e4' }
    const gate = { ...current.gates[0], id: 3 }
    const envelope = { ...current.envelopes[0], envelope_id: 'env2' }
    const merged = applyTail(
      current,
      evts,
      tail({
        events: [evts[2], newEvent],
        gates: [current.gates[1], gate],
        envelopes: [current.envelopes[0], envelope],
        usage_delta: { read: 10, written: 5 },
        cursors: { events: 4, phases: 2, gates: 3, envelopes: 2 },
      }),
    )
    expect(merged.events.map((e) => e.event_id)).toEqual(['e1', 'e2', 'e3', 'e4'])
    expect(merged.detail.gates.map((g) => g.id)).toEqual([1, 2, 3])
    expect(merged.detail.envelopes.map((e) => e.envelope_id)).toEqual(['env1', 'env2'])
    expect(merged.detail.usage).toEqual({ read: 160, written: 35 })
    expect(merged.detail.cursors).toEqual({ events: 4, phases: 2, gates: 3, envelopes: 2 })
  })

  it('keeps the events array when nothing is new', () => {
    const evts = events()
    expect(applyTail(detail(), evts, tail()).events).toBe(evts)
  })
})

describe('cursorsOf', () => {
  it('prefers the cursors of the detail', () => {
    const current = { ...detail(), cursors: { events: 9, phases: 8, gates: 7, envelopes: 6 } }
    expect(cursorsOf(current, events())).toEqual({ events: 9, phases: 8, gates: 7, envelopes: 6 })
  })

  it('falls back to the rows', () => {
    expect(cursorsOf(detail(), events())).toEqual({ events: 3, phases: 0, gates: 2, envelopes: 0 })
  })
})

describe('fetchPhasePrompts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('asks the prompts endpoint of the phase', async () => {
    const data = { system: 'S', user: 'U' }
    const fetchMock = vi.fn(
      async (_url: string) => new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] })),
    )
    vi.stubGlobal('fetch', fetchMock)
    expect(await fetchPhasePrompts('r ok', 'p1')).toEqual(data)
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r%20ok/phases/p1/prompts')
  })
})

describe('checksLabel', () => {
  it('counts checks and failures', () => {
    expect(checksLabel([])).toBe('0')
    expect(checksLabel([{ item: 'a', ok: true, note: '' }])).toBe('1')
    expect(
      checksLabel([
        { item: 'a', ok: true, note: '' },
        { item: 'b', ok: false, note: '' },
      ]),
    ).toBe('1 z 2 selhalo')
  })
})

describe('slotWaitLabel', () => {
  it('names how many runs are ahead of a waiting test phase', () => {
    expect(slotWaitLabel({ ahead: 1, slots: 1 })).toBe('čeká na volný slot testů, před ní 1 běh')
    expect(slotWaitLabel({ ahead: 3, slots: 1 })).toBe('čeká na volný slot testů, před ní 3 běhy')
    expect(slotWaitLabel({ ahead: 5, slots: 2 })).toBe('čeká na volný slot testů, před ní 5 běhů')
  })
})

describe('excerpt', () => {
  it('leaves short text alone', () => {
    expect(excerpt('keep what this says', 50)).toBe('keep what this says')
  })

  it('cuts at a word boundary and ends with an ellipsis', () => {
    const cut = excerpt('keep what this says', 13)
    expect(cut).toBe('keep what…')
    expect(cut.length).toBeLessThanOrEqual(13)
  })

  it('cuts a single long word hard, still with an ellipsis', () => {
    expect(excerpt('abcdefghij', 5)).toBe('abcd…')
  })
})


describe('archived runs', () => {
  afterEach(() => vi.unstubAllGlobals())

  function stubFetch() {
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response(JSON.stringify({ ok: true, data: { runs: [], tasks: [] }, error: null, warnings: [] })),
    )
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  it('every run but a running one is finished', () => {
    const states = ['running', 'succeeded', 'failed', 'aborted', 'stopped'] as const
    expect(states.filter((state) => isFinished(summary({ state })))).toEqual([
      'succeeded',
      'failed',
      'aborted',
      'stopped',
    ])
  })

  it('asks for the archived list only in the archived view', async () => {
    const fetchMock = stubFetch()
    await fetchRuns()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/runs')
    await fetchRuns(true)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/runs?archived=1')
  })

  it('posts the archive and delete actions', async () => {
    const fetchMock = stubFetch()
    await archiveRun('r/1')
    await unarchiveRun('r1')
    await deleteRun('r1')
    await archiveFinishedRuns()
    await deleteArchivedRuns()
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/repos/haifa/runs/r%2F1/archive', 'POST'],
      ['/api/repos/haifa/runs/r1/unarchive', 'POST'],
      ['/api/repos/haifa/runs/r1/delete', 'POST'],
      ['/api/repos/haifa/runs/archive-finished', 'POST'],
      ['/api/repos/haifa/runs/delete-archived', 'POST'],
    ])
  })
})

describe('shownState', () => {
  it('shows a running run with a pause as pausing or paused', () => {
    expect(shownState({ state: 'running', pause: null })).toBe('running')
    expect(shownState({ state: 'running', pause: 'pausing' })).toBe('pausing')
    expect(shownState({ state: 'running', pause: 'paused' })).toBe('paused')
    expect(shownState({ state: 'stopped', pause: 'paused' })).toBe('stopped')
    expect(shownState({ state: 'succeeded' })).toBe('succeeded')
  })
})

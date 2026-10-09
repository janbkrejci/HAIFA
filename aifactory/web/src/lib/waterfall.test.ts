import { describe, expect, it } from 'vitest'
import { AGENT_FALLBACK_COLORS } from './events'
import type { AgentSession, PhaseRow, RunDetail, TraceEvent } from './runs'
import {
  MIN_BLOCK_PCT,
  REQ_ZONE_PCT,
  blockDurationMs,
  buildLanes,
  buildTimeline,
  contextLabel,
  laneContext,
  toolTicks,
} from './waterfall'
import { detail as fixtureDetail } from '@/test/runsFixtures'

const T0 = Date.parse('2026-01-01T10:00:00Z')

function at(sec: number): string {
  return new Date(T0 + sec * 1000).toISOString()
}

function phase(over: Partial<PhaseRow> & { phase_id: string }): PhaseRow {
  return {
    adw_id: 'r',
    seq: 1,
    name: over.phase_id,
    kind: 'agent',
    owner: 'planner',
    description: null,
    status: 'success',
    attempt: 1,
    retries: 0,
    error: null,
    started_at: at(0),
    ended_at: at(10),
    harness: null,
    model: null,
    tokens: 0,
    cost: 0,
    usage: null,
    duration_s: null,
    ...over,
  }
}

function run(phases: PhaseRow[], agents: AgentSession[] = [], state: 'running' | 'succeeded' = 'succeeded'): RunDetail {
  const base = fixtureDetail({ state })
  return { ...base, phases, agents, run: { ...base.run, started_at: at(0), ended_at: state === 'running' ? null : at(600) } }
}

function agent(over: Partial<AgentSession> & { agent: string }): AgentSession {
  return {
    coding_agent: null,
    model: null,
    session_id: null,
    created_at: null,
    last_used_at: null,
    ...over,
  }
}

function event(over: Partial<TraceEvent>): TraceEvent {
  return {
    rowid: 1,
    event_id: 'e',
    adw_id: 'r',
    phase_id: null,
    parent_id: null,
    type: 'tool_call',
    name: null,
    payload: {},
    tokens: null,
    started_at: null,
    ended_at: null,
    ...over,
  }
}

function overlaps(blocks: { left: number; width: number }[]): boolean {
  const sorted = [...blocks].sort((a, b) => a.left - b.left)
  return sorted.some((b, i) => i > 0 && b.left < sorted[i - 1]!.left + sorted[i - 1]!.width - 1e-9)
}

describe('buildLanes', () => {
  it('orders engineer, code, then agents by first appearance', () => {
    const lanes = buildLanes(
      run([
        phase({ phase_id: 'a', seq: 3, owner: 'planner' }),
        phase({ phase_id: 'b', seq: 2, owner: 'builder' }),
        phase({ phase_id: 'c', seq: 4, kind: 'code', owner: 'git' }),
        phase({ phase_id: 'r', seq: 1, kind: 'engineer', owner: 'engineer' }),
      ]),
      [],
    )
    expect(lanes.map((l) => l.id)).toEqual(['engineer', 'code', 'agent:builder', 'agent:planner'])
  })

  it('has no code lane without a code phase', () => {
    const lanes = buildLanes(run([phase({ phase_id: 'a' })]), [])
    expect(lanes.map((l) => l.id)).toEqual(['engineer', 'agent:planner'])
  })

  it('gives an agent in two phases one lane', () => {
    const lanes = buildLanes(
      run([
        phase({ phase_id: 'a', seq: 2 }),
        phase({ phase_id: 'b', seq: 3, owner: 'builder' }),
        phase({ phase_id: 'c', seq: 5 }),
      ]),
      [],
    )
    const planner = lanes.filter((l) => l.id === 'agent:planner')
    expect(planner).toHaveLength(1)
    expect(planner[0]!.phases.map((p) => p.phase_id)).toEqual(['a', 'c'])
  })

  it('puts every code phase into one lane', () => {
    const lanes = buildLanes(
      run([
        phase({ phase_id: 'g', seq: 1, kind: 'code', owner: 'git', name: 'git' }),
        phase({ phase_id: 'q', seq: 2, kind: 'code', owner: 'tests', name: 'quality:test' }),
      ]),
      [],
    )
    expect(lanes.filter((l) => l.kind === 'code')).toHaveLength(1)
    expect(lanes.find((l) => l.id === 'code')!.phases.map((p) => p.name)).toEqual(['git', 'quality:test'])
  })

  it('falls back to the palette for an empty color', () => {
    const phases = [phase({ phase_id: 'a' })]
    const empty = buildLanes(run(phases, [agent({ agent: 'planner', color: '' })]), [])
    expect(empty.find((l) => l.id === 'agent:planner')!.color).toBe(AGENT_FALLBACK_COLORS[0])
    const set = buildLanes(run(phases, [agent({ agent: 'planner', color: '#112233' })]), [])
    expect(set.find((l) => l.id === 'agent:planner')!.color).toBe('#112233')
    const start = event({ type: 'agent_start', phase_id: 'a', name: 'planner', payload: { color: '#abcdef', model: 'gpt-5' } })
    const fromStart = buildLanes(run(phases), [start]).find((l) => l.id === 'agent:planner')!
    expect(fromStart.color).toBe('#abcdef')
    expect(fromStart.model).toBe('gpt-5')
  })
})

describe('lane context', () => {
  it('is unknown without a window and labels small fills', () => {
    expect(laneContext(agent({ agent: 'x', context_tokens: 10 }))).toBeNull()
    expect(laneContext(undefined)).toBeNull()
    expect(contextLabel(laneContext(agent({ agent: 'x', context_tokens: 1000, context_window: 200_000 }))!)).toBe('0.5%')
    expect(contextLabel(laneContext(agent({ agent: 'x', context_tokens: 74_000, context_window: 200_000 }))!)).toBe('37%')
  })
})

describe('buildTimeline', () => {
  it('never overlaps blocks and keeps them in the track', () => {
    const phases = [
      phase({ phase_id: 'a', seq: 1, started_at: at(0), ended_at: at(0) }),
      phase({ phase_id: 'b', seq: 2, started_at: at(0), ended_at: at(0), kind: 'code' }),
      phase({ phase_id: 'c', seq: 3, started_at: at(0), ended_at: at(200) }),
      phase({ phase_id: 'd', seq: 4, started_at: at(200), ended_at: at(200), kind: 'code' }),
      phase({ phase_id: 'e', seq: 5, started_at: at(201), ended_at: at(600) }),
    ]
    const { blocks, zonePct } = buildTimeline(run(phases), T0 + 1_000_000)
    const geoms = Object.values(blocks)
    expect(geoms).toHaveLength(5)
    expect(overlaps(geoms)).toBe(false)
    for (const g of geoms) {
      expect(g.left).toBeGreaterThanOrEqual(zonePct)
      expect(g.left + g.width).toBeLessThanOrEqual(100 + 1e-9)
    }
  })

  it('does not overlap two phases with the same times (fixture)', () => {
    const { blocks } = buildTimeline(fixtureDetail(), Date.now())
    expect(overlaps([blocks.p1!, blocks.p2!])).toBe(false)
  })

  it('widens a zero-length phase to the minimum', () => {
    const phases = [
      phase({ phase_id: 'a', seq: 1, started_at: at(0), ended_at: at(300) }),
      phase({ phase_id: 'b', seq: 2, started_at: at(300), ended_at: at(300), kind: 'code' }),
      phase({ phase_id: 'c', seq: 3, started_at: at(300), ended_at: at(600) }),
    ]
    const { blocks } = buildTimeline(run(phases), T0)
    expect(blocks.b!.width).toBeGreaterThanOrEqual(MIN_BLOCK_PCT - 1e-9)
    expect(overlaps(Object.values(blocks))).toBe(false)
  })

  it('reserves the request zone for the engineer phase', () => {
    const phases = [
      phase({ phase_id: 'req', seq: 1, kind: 'engineer', owner: 'engineer', started_at: at(0), ended_at: at(5) }),
      phase({ phase_id: 'a', seq: 2, started_at: at(5), ended_at: at(100) }),
      phase({ phase_id: 'b', seq: 3, started_at: at(100), ended_at: at(200), kind: 'code' }),
    ]
    const tl = buildTimeline(run(phases), T0)
    expect(tl.zonePct).toBe(REQ_ZONE_PCT)
    expect(tl.requestId).toBe('req')
    expect(tl.blocks.req!.left).toBeCloseTo(0.4)
    expect(tl.blocks.req!.width).toBeCloseTo(15.2)
    expect(tl.blocks.a!.left).toBeGreaterThanOrEqual(REQ_ZONE_PCT)
    expect(tl.blocks.b!.left).toBeGreaterThanOrEqual(REQ_ZONE_PCT)
    expect(tl.ticks[0]!.pct).toBe(REQ_ZONE_PCT)
  })

  it('has no geometry for a queued phase', () => {
    const tl = buildTimeline(run([phase({ phase_id: 'q', status: 'queued', started_at: null, ended_at: null })]), T0)
    expect(tl.blocks.q).toBeUndefined()
  })

  it('grows a running block with now', () => {
    const phases = [
      phase({ phase_id: 'a', seq: 1, started_at: at(0), ended_at: at(30) }),
      phase({ phase_id: 'b', seq: 2, status: 'running', started_at: at(30), ended_at: null }),
    ]
    const detail = run(phases, [], 'running')
    const p = phases[1]!
    expect(blockDurationMs(p, T0 + 40_000)).toBe(10_000)
    expect(blockDurationMs(p, T0 + 70_000)).toBe(40_000)
    const early = buildTimeline(detail, T0 + 40_000).blocks.b!
    const late = buildTimeline(detail, T0 + 300_000).blocks.b!
    expect(late.width).toBeGreaterThan(early.width)
  })
})

describe('toolTicks', () => {
  it('marks a failed quality check and an ok tool call', () => {
    const p = phase({ phase_id: 'q', kind: 'code', started_at: at(0), ended_at: at(10) })
    const ticks = toolTicks(
      p,
      [
        event({ phase_id: 'q', name: 'quality:test', started_at: at(5), payload: { command: 'pytest', returncode: 1 } }),
        event({ phase_id: 'q', name: 'Read', started_at: at(8), payload: { tool: 'Read', ok: true } }),
        event({ phase_id: 'q', name: 'no time', payload: { tool: 'Read' } }),
        event({ phase_id: 'other', started_at: at(5) }),
      ],
      T0,
    )
    expect(ticks).toEqual([
      { x: 50, ok: false },
      { x: 80, ok: true },
    ])
  })
})

describe('buildTimeline with many phases', () => {
  it('keeps blocks in the track without overlap even past the floor', () => {
    const phases = Array.from({ length: 40 }, (_, i) =>
      phase({ phase_id: `p${i}`, seq: i, started_at: at(i * 10), ended_at: at(i * 10 + (i % 3 ? 0 : 50)) }),
    )
    const { blocks } = buildTimeline(run(phases), T0)
    const geoms = Object.values(blocks)
    expect(overlaps(geoms)).toBe(false)
    for (const g of geoms) {
      expect(g.width).toBeGreaterThan(0)
      expect(g.left + g.width).toBeLessThanOrEqual(100 + 1e-9)
    }
  })

  it('keeps the floor for a dozen zero-length phases among long ones', () => {
    const phases = Array.from({ length: 12 }, (_, i) =>
      phase({ phase_id: `p${i}`, seq: i, started_at: at(i * 50), ended_at: at(i * 50 + (i % 2 ? 0 : 50)) }),
    )
    const { blocks } = buildTimeline(run(phases), T0)
    for (const g of Object.values(blocks)) expect(g.width).toBeGreaterThanOrEqual(MIN_BLOCK_PCT - 1e-9)
    expect(overlaps(Object.values(blocks))).toBe(false)
  })
})

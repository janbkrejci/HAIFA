// Waterfall (gantt) layout of a run, ported from the sssf visualizer's SessionTrace.vue.
// Pure functions: lanes, the time axis and block geometry, testable without a DOM.
import { agentColor, eventOk, parseAgentStart } from './events'
import { axisTicks, ts } from './format'
import {
  bySeq,
  type AgentSession,
  type AgentStartPayload,
  type PhaseKind,
  type PhaseRow,
  type RunDetail,
  type TraceEvent,
} from './runs'

/** Track-% reserved at the start of the timeline for the engineer's request. */
export const REQ_ZONE_PCT = 16
/** Readable floor for a block's width, in track-%. */
export const MIN_BLOCK_PCT = 3.5
/** Hair of right margin, in track-%. */
export const RIGHT_MARGIN_PCT = 0.4
export const ENGINEER_COLOR = '#e8b64a'
export const CODE_COLOR = '#5ad2dd'

export interface LaneContext {
  used: number
  window: number
  /** 0–100, uncapped by the floor applied to the bar's width. */
  pct: number
}

export interface Lane {
  id: string
  kind: PhaseKind
  label: string
  /** Model driving this lane's agent — rendered with its provider icon. */
  model: string | null
  /** Context-window occupancy, or null while unknown. */
  context: LaneContext | null
  meta: string | null
  color: string
  phases: PhaseRow[]
}

export interface BlockGeom {
  left: number
  width: number
}

export function sortPhases(phases: PhaseRow[]): PhaseRow[] {
  return [...phases].sort(bySeq)
}

/** Occupancy for an agent lane; null unless both numbers are known. */
export function laneContext(info?: AgentSession): LaneContext | null {
  const used = info?.context_tokens ?? 0
  const window = info?.context_window ?? 0
  if (!used || !window) return null
  return { used, window, pct: Math.min(100, (used / window) * 100) }
}

/** Sub-1% occupancy is common and real; round it away and the bar reads empty. */
export function contextLabel(ctx: LaneContext): string {
  return ctx.pct < 1 ? `${ctx.pct.toFixed(1)}%` : `${Math.round(ctx.pct)}%`
}

/** Keep a non-zero fill visible — the exact numbers ride in the label and tooltip. */
export function contextFill(ctx: LaneContext): string {
  return `${Math.max(ctx.pct, 2)}%`
}

/** The first agent_start of each owner (the owner of its phase, else the event name). */
export function ownerStarts(phases: PhaseRow[], events: TraceEvent[]): Record<string, AgentStartPayload> {
  const ownerByPhase = new Map<string, string | null>(phases.map((p) => [p.phase_id, p.owner]))
  const out: Record<string, AgentStartPayload> = {}
  for (const e of events) {
    if (e.type !== 'agent_start') continue
    const owner = (e.phase_id ? ownerByPhase.get(e.phase_id) : null) ?? e.name
    if (!owner || out[owner]) continue
    const payload = parseAgentStart(e)
    if (payload) out[owner] = payload
  }
  return out
}

/** Engineer, code (every code phase) and one lane per agent in order of first appearance. */
export function buildLanes(detail: RunDetail, events: TraceEvent[]): Lane[] {
  const phases = sortPhases(detail.phases ?? [])
  const owners: string[] = []
  for (const p of phases) {
    if (p.kind === 'agent' && p.owner && !owners.includes(p.owner)) owners.push(p.owner)
  }
  const code = phases.filter((p) => p.kind === 'code')
  const lanes: Lane[] = [
    {
      id: 'engineer',
      kind: 'engineer',
      label: detail.session?.engineer ?? 'engineer',
      model: null,
      context: null,
      meta: 'požadavek',
      color: ENGINEER_COLOR,
      phases: phases.filter((p) => p.kind === 'engineer'),
    },
  ]
  if (code.length) {
    lanes.push({
      id: 'code',
      kind: 'code',
      label: 'kód',
      model: null,
      context: null,
      meta: 'workspace',
      color: CODE_COLOR,
      phases: code,
    })
  }
  const starts = ownerStarts(phases, events)
  for (const [i, owner] of owners.entries()) {
    const info = (detail.agents ?? []).find((a) => a.agent === owner)
    const start = starts[owner]
    lanes.push({
      id: `agent:${owner}`,
      kind: 'agent',
      label: owner,
      model: info?.model ?? start?.model ?? null,
      context: laneContext(info),
      meta: null,
      color: agentColor(info?.color, start?.color, i),
      phases: phases.filter((p) => p.kind === 'agent' && p.owner === owner),
    })
  }
  return lanes
}

/** Where a phase ends on the timeline: now while running, else its end, else its start. */
export function phaseEndMs(p: PhaseRow, now: number): number {
  const start = ts(p.started_at)
  if (p.status === 'running') return now
  const end = ts(p.ended_at)
  return Number.isFinite(end) ? end : start
}

/** A phase's duration in ms (growing while it runs), NaN without a start. */
export function blockDurationMs(p: PhaseRow, now: number): number {
  const start = ts(p.started_at)
  if (!Number.isFinite(start)) return NaN
  const end = p.status === 'running' ? now : ts(p.ended_at)
  if (!Number.isFinite(end)) return NaN
  return Math.max(end - start, 0)
}

export interface Timeline {
  t0: number
  t1: number
  zonePct: number
  requestId: string | null
  origin: number
  postSpan: number
  ticks: { pct: number; label: string }[]
  blocks: Record<string, BlockGeom>
}

/** True while the run or any of its phases still runs. */
export function isLive(detail: RunDetail): boolean {
  return detail.run.state === 'running' || (detail.phases ?? []).some((p) => p.status === 'running')
}

export function buildTimeline(detail: RunDetail, now: number): Timeline {
  const phases = sortPhases(detail.phases ?? [])
  let t0 = Infinity
  let t1 = -Infinity
  const starts = [ts(detail.session?.started_at), ts(detail.run.started_at)]
  const ends = [ts(detail.session?.ended_at), ts(detail.run.ended_at)]
  for (const a of starts) if (Number.isFinite(a)) t0 = Math.min(t0, a)
  for (const b of ends) if (Number.isFinite(b)) t1 = Math.max(t1, b)
  for (const p of phases) {
    const a = ts(p.started_at)
    const b = ts(p.ended_at)
    if (Number.isFinite(a)) {
      t0 = Math.min(t0, a)
      t1 = Math.max(t1, a)
    }
    if (Number.isFinite(b)) t1 = Math.max(t1, b)
  }
  if (isLive(detail)) t1 = Math.max(t1, now)
  if (!Number.isFinite(t0)) {
    t0 = now
    t1 = now + 1000
  }
  if (!Number.isFinite(t1) || t1 - t0 < 1000) t1 = t0 + 1000

  // The engineer's request opens the run and owns an exclusive leading zone.
  const request = phases.find((p) => p.kind === 'engineer' && Number.isFinite(ts(p.started_at))) ?? null
  const zonePct = request ? REQ_ZONE_PCT : 0

  // The post-request timeline begins at the earliest non-engineer phase start.
  let origin = t0
  if (request) {
    let earliest = Infinity
    for (const p of phases) {
      if (p.kind === 'engineer') continue
      const s = ts(p.started_at)
      if (Number.isFinite(s)) earliest = Math.min(earliest, s)
    }
    if (Number.isFinite(earliest)) origin = Math.max(earliest, t0)
    else {
      const end = ts(request.ended_at ?? request.started_at)
      origin = Number.isFinite(end) ? Math.max(end, t0) : t0
    }
  }
  const postSpan = Math.max(t1 - origin, 1000)

  const ticks = axisTicks(postSpan, 7).map((t) => ({
    pct: zonePct + (t.pct * (100 - zonePct)) / 100,
    label: t.label,
  }))

  // Sequential layout: a block widened to the floor pushes every later block right,
  // then the whole layout is scaled back into the track. Blocks never stack.
  const avail = 100 - zonePct - RIGHT_MARGIN_PCT
  const timed = phases
    .filter((p) => p.phase_id !== request?.phase_id && Number.isFinite(ts(p.started_at)))
    .map((p, order) => {
      const start = ts(p.started_at)
      const end = Math.max(phaseEndMs(p, now), start)
      return {
        id: p.phase_id,
        start,
        order,
        left: ((start - origin) / postSpan) * avail,
        width: ((end - start) / postSpan) * avail,
      }
    })
    .sort((a, b) => a.start - b.start || a.order - b.order)

  // Each block is a gap after the previous edge plus its width; a block widened to the
  // floor pushes every later one right instead of overlapping it.
  let shift = 0
  let prevEdge = 0
  const rows: { id: string; gap: number; width: number; floored: boolean }[] = []
  for (const b of timed) {
    let left = b.left + shift
    if (left < prevEdge) {
      shift += prevEdge - left
      left = prevEdge
    }
    const width = Math.max(b.width, MIN_BLOCK_PCT)
    shift += width - b.width
    rows.push({ id: b.id, gap: left - prevEdge, width, floored: width <= MIN_BLOCK_PCT })
    prevEdge = left + width
  }

  // Squeeze an overflow back into the track: gaps and naturally wide blocks shrink,
  // blocks at the floor keep it (a block squeezed below the floor joins them).
  if (prevEdge > avail) {
    const fixed = () => rows.filter((r) => r.floored).length * MIN_BLOCK_PCT
    for (;;) {
      if (fixed() >= avail) {
        // Too many phases for the floor: scale everything evenly.
        const total = rows.reduce((sum, r) => sum + r.gap + r.width, 0)
        const k = avail / total
        for (const r of rows) {
          r.gap *= k
          r.width *= k
        }
        break
      }
      const flexible = rows.reduce((sum, r) => sum + r.gap + (r.floored ? 0 : r.width), 0)
      const k = flexible > 0 ? Math.min(1, (avail - fixed()) / flexible) : 1
      const under = rows.filter((r) => !r.floored && r.width * k < MIN_BLOCK_PCT)
      if (under.length) {
        for (const r of under) {
          r.floored = true
          r.width = MIN_BLOCK_PCT
        }
        continue
      }
      for (const r of rows) {
        r.gap *= k
        if (!r.floored) r.width *= k
      }
      break
    }
  }

  const blocks: Record<string, BlockGeom> = {}
  let edge = zonePct
  for (const r of rows) {
    const left = edge + r.gap
    blocks[r.id] = { left, width: r.width }
    edge = left + r.width
  }
  if (request) blocks[request.phase_id] = { left: 0.4, width: zonePct - 0.8 }

  return { t0, t1, zonePct, requestId: request?.phase_id ?? null, origin, postSpan, ticks, blocks }
}

/** Tool-call marks inside a phase block, in %-of-block; a failed call is not ok. */
export function toolTicks(p: PhaseRow, events: TraceEvent[], now: number): { x: number; ok: boolean }[] {
  const start = ts(p.started_at)
  if (!Number.isFinite(start)) return []
  const width = Math.max(phaseEndMs(p, now) - start, 1)
  const out: { x: number; ok: boolean }[] = []
  for (const e of events) {
    if (e.type !== 'tool_call' || e.phase_id !== p.phase_id) continue
    const t = ts(e.started_at)
    if (!Number.isFinite(t)) continue
    out.push({ x: Math.min(Math.max(((t - start) / width) * 100, 1), 99), ok: eventOk(e) })
  }
  return out
}

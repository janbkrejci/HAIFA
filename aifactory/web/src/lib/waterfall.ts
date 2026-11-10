// Waterfall (gantt) layout of a run, ported from the sssf visualizer's SessionTrace.vue.
// Pure functions: lanes, the time axis and block geometry, testable without a DOM.
import { agentColor, eventOk, mergeToolStarts, parseAgentStart } from './events'
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

/** Track-% of the visible track reserved at the start of the timeline for the engineer's request. */
export const REQ_ZONE_PCT = 16
/** Hair of right margin, in track-% of the visible track. */
export const RIGHT_MARGIN_PCT = 0.4
/** Readable floor for a timed block's width, in px. */
export const MIN_BLOCK_PX = 132
/** Space kept between two neighbouring blocks, in px. */
export const BLOCK_GAP_PX = 6
/** Width of a queued block (a phase without a start), in px. */
export const QUEUED_BLOCK_PX = 170
/** Closest two axis labels may sit, in px. */
export const MIN_TICK_GAP_PX = 72
/** Track width assumed before (or without) a measurement, in px. */
export const DEFAULT_TRACK_PX = 1000
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
    const ownerPhases = phases.filter((p) => p.kind === 'agent' && p.owner === owner)
    lanes.push({
      id: `agent:${owner}`,
      kind: 'agent',
      label: owner,
      model: info?.model ?? start?.model ?? ownerPhases.find((p) => p.model)?.model ?? null,
      context: laneContext(info),
      meta: null,
      color: agentColor(info?.color, start?.color, i),
      phases: ownerPhases,
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
  /** Width of the whole track canvas in px: the visible track, or more when the blocks need it. */
  width: number
  /** True when the canvas is wider than the visible track (the gantt scrolls). */
  overflow: boolean
  /** Positions in %-of-canvas; the axis follows the same warping as the blocks. */
  ticks: { pct: number; label: string }[]
  /** Geometry in %-of-canvas of every phase, queued ones included. */
  blocks: Record<string, BlockGeom>
}

/** True while the run or any of its phases still runs. */
export function isLive(detail: RunDetail): boolean {
  return detail.run.state === 'running' || (detail.phases ?? []).some((p) => p.status === 'running')
}

interface TimedBlock {
  id: string
  start: number
  end: number
  order: number
  /** Natural position and width at full time scale, in px after the request zone. */
  left: number
  width: number
}

interface PlacedBlock {
  id: string
  start: number
  end: number
  left: number
  width: number
}

/**
 * Sequential layout at time scale `k` (0–1 of the natural scale): a block keeps its natural
 * gap after the previous one, is widened to the floor and pushed right past the previous
 * edge plus a gap, so no two blocks ever share a horizontal range.
 */
function placeTimed(timed: TimedBlock[], k: number): PlacedBlock[] {
  let shift = 0
  let prevEdge = -Infinity
  const out: PlacedBlock[] = []
  for (const b of timed) {
    let left = b.left * k + shift
    const minLeft = out.length ? prevEdge + BLOCK_GAP_PX : 0
    if (left < minLeft) {
      shift += minLeft - left
      left = minLeft
    }
    const width = Math.max(b.width * k, MIN_BLOCK_PX)
    shift += width - b.width * k
    out.push({ id: b.id, start: b.start, end: b.end, left, width })
    prevEdge = left + width
  }
  return out
}

function placedEnd(placed: PlacedBlock[]): number {
  const last = placed[placed.length - 1]
  return last ? last.left + last.width : 0
}

/** Maps a time onto the warped layout through the block edges (monotonic anchors). */
function timeMapper(anchors: { t: number; x: number }[]): (t: number) => number {
  return (t: number) => {
    if (t <= anchors[0]!.t) return anchors[0]!.x
    for (let i = 1; i < anchors.length; i++) {
      const a = anchors[i - 1]!
      const b = anchors[i]!
      if (t <= b.t) return b.t > a.t ? a.x + ((t - a.t) / (b.t - a.t)) * (b.x - a.x) : b.x
    }
    return anchors[anchors.length - 1]!.x
  }
}

/**
 * The waterfall's geometry for a track `trackPx` wide. Blocks keep a readable floor and a gap;
 * a run that fits is squeezed into the track, a longer one widens the canvas (`width`) so
 * the gantt scrolls instead of shrinking or stacking its blocks. Queued phases follow the
 * timed ones in order.
 */
export function buildTimeline(detail: RunDetail, now: number, trackPx: number = DEFAULT_TRACK_PX): Timeline {
  const track = Number.isFinite(trackPx) && trackPx > 0 ? trackPx : DEFAULT_TRACK_PX
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
  const zonePx = request ? (REQ_ZONE_PCT * track) / 100 : 0

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

  const marginPx = (RIGHT_MARGIN_PCT * track) / 100
  const avail = Math.max(track - zonePx - marginPx, 0)
  const scale = avail / postSpan
  const timed: TimedBlock[] = phases
    .filter((p) => p.phase_id !== request?.phase_id && Number.isFinite(ts(p.started_at)))
    .map((p, order) => {
      const start = ts(p.started_at)
      const end = Math.max(phaseEndMs(p, now), start)
      return {
        id: p.phase_id,
        start,
        end,
        order,
        left: (start - origin) * scale,
        width: (end - start) * scale,
      }
    })
    .sort((a, b) => a.start - b.start || a.order - b.order)
  const queued = phases.filter((p) => p.phase_id !== request?.phase_id && !Number.isFinite(ts(p.started_at)))
  const queuedPx = queued.length * (BLOCK_GAP_PX + QUEUED_BLOCK_PX)

  // Squeeze the time scale until the timed blocks fit beside the queued ones. When even the
  // floors and gaps alone do not fit, the target grows to them: the canvas widens.
  const floorPx = placedEnd(placeTimed(timed, 0))
  const target = Math.max(avail - queuedPx, floorPx)
  let k = 1
  if (placedEnd(placeTimed(timed, 1)) > target) {
    let lo = 0
    let hi = 1
    for (let i = 0; i < 40; i++) {
      const mid = (lo + hi) / 2
      if (placedEnd(placeTimed(timed, mid)) <= target) lo = mid
      else hi = mid
    }
    k = lo
  }
  const placed = placeTimed(timed, k)
  let edge = placedEnd(placed)
  const queuedPlaced: { id: string; left: number; width: number }[] = []
  for (const p of queued) {
    const left = edge + (placed.length || queuedPlaced.length ? BLOCK_GAP_PX : 0)
    queuedPlaced.push({ id: p.phase_id, left, width: QUEUED_BLOCK_PX })
    edge = left + QUEUED_BLOCK_PX
  }
  const postPx = Math.max(avail, edge)
  const width = zonePx + postPx + marginPx
  const overflow = width > track + 0.5
  const pct = (px: number) => (px / width) * 100
  const zonePct = request ? (REQ_ZONE_PCT * track) / width : 0

  // The axis follows the blocks: their edges anchor time to x, ticks too close are dropped.
  const anchors: { t: number; x: number }[] = [{ t: origin, x: 0 }]
  const push = (t: number, x: number) => {
    const last = anchors[anchors.length - 1]!
    if (t >= last.t && x >= last.x) anchors.push({ t, x })
  }
  for (const b of placed) {
    push(b.start, b.left)
    push(b.end, b.left + b.width)
  }
  const lastAnchor = anchors[anchors.length - 1]!
  if (t1 > lastAnchor.t) push(t1, lastAnchor.x + (t1 - lastAnchor.t) * scale * k)
  const toX = timeMapper(anchors)
  const ticks: { pct: number; label: string }[] = []
  let lastTickPx = -Infinity
  const tickCount = Math.max(7, Math.round(postPx / (2 * MIN_TICK_GAP_PX)))
  for (const t of axisTicks(postSpan, tickCount)) {
    const x = toX(origin + (t.pct / 100) * postSpan)
    if (ticks.length && x - lastTickPx < MIN_TICK_GAP_PX) continue
    ticks.push({ pct: zonePct + pct(x), label: t.label })
    lastTickPx = x
  }

  const blocks: Record<string, BlockGeom> = {}
  for (const b of [...placed, ...queuedPlaced]) {
    blocks[b.id] = { left: zonePct + pct(b.left), width: pct(b.width) }
  }
  if (request) blocks[request.phase_id] = { left: pct((0.4 * track) / 100), width: pct(zonePx - (0.8 * track) / 100) }

  return {
    t0,
    t1,
    zonePct,
    requestId: request?.phase_id ?? null,
    origin,
    postSpan,
    width,
    overflow,
    ticks,
    blocks,
  }
}

/** Tool-call marks inside a phase block, in %-of-block; a failed call is not ok. */
export function toolTicks(p: PhaseRow, events: TraceEvent[], now: number): { x: number; ok: boolean }[] {
  const start = ts(p.started_at)
  if (!Number.isFinite(start)) return []
  const width = Math.max(phaseEndMs(p, now) - start, 1)
  const out: { x: number; ok: boolean }[] = []
  for (const e of mergeToolStarts(events)) {
    if ((e.type !== 'tool_call' && e.type !== 'tool_start') || e.phase_id !== p.phase_id) continue
    const t = ts(e.started_at)
    if (!Number.isFinite(t)) continue
    out.push({ x: Math.min(Math.max(((t - start) / width) * 100, 1), 99), ok: eventOk(e) })
  }
  return out
}

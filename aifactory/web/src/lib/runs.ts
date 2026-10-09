// Task runs and their trace, as served by /api/runs (aifactory/web/runs.py).
// Trace shapes follow the sssf visualizer's shared/types.ts, with JSON columns parsed.
import { getApi, postApi } from './api'
import { plural } from './format'

export type PhaseKind = 'engineer' | 'agent' | 'code'

export type RunState = 'running' | 'succeeded' | 'failed' | 'aborted' | 'stopped'

/** A running run's pause (`factory task pause`): asked for, or waiting before its next phase. */
export type RunPause = 'pausing' | 'paused'

/**
 * The state a run is shown in: a running run with a pause shows `pausing` (the current
 * phase still runs) or `paused` (it waits before the next phase); otherwise its state.
 */
export function shownState(run: { state: string | null; pause?: string | null }): string | null {
  if (run.state === 'running' && (run.pause === 'paused' || run.pause === 'pausing')) return run.pause
  return run.state
}

/** A test phase waiting for a machine-wide test slot (`test_slots`). */
export interface SlotWait {
  ahead: number | null
  slots: number | null
}

export interface PhaseDot {
  seq: number | null
  name: string | null
  status: string | null
  slot_wait?: SlotWait | null
}

/** "čeká na volný slot testů, před ní 2 běhy" for a waiting test phase. */
export function slotWaitLabel(wait: SlotWait): string {
  const ahead = wait.ahead ?? 0
  return `čeká na volný slot testů, před ní ${ahead} ${plural(ahead, 'běh', 'běhy', 'běhů')}`
}

/** A request longer than this many characters starts collapsed in the run detail. */
export const REQUEST_PREVIEW_CHARS = 1200

/**
 * `text` cut to at most `max` characters: at the last whitespace before the cut,
 * ending with "…" — never in the middle of a word. Short text comes back unchanged.
 */
export function excerpt(text: string, max: number): string {
  if (text.length <= max) return text
  const head = text.slice(0, Math.max(0, max - 1))
  const space = head.search(/\s\S*$/)
  const cut = space > 0 ? head.slice(0, space) : head
  return `${cut.trimEnd()}…`
}

const PR_STATE_LABELS: Record<string, string> = {
  open: 'otevřený',
  merged: 'sloučený',
  closed: 'zavřený',
  draft: 'rozpracovaný',
}

/** Czech state of a pull request (`open` → otevřený); an unknown state unchanged. */
export function prStateLabel(state: string | null | undefined): string {
  if (!state) return '—'
  return PR_STATE_LABELS[state] ?? state
}

export interface RunPr {
  url: string
  pr_id: string
  state: string
  /** 'auto-merge' or 'operator' once factory merged the PR. */
  merged_by?: string | null
  /** Why auto-merge left the PR open. */
  auto_merge_error?: string | null
}

export interface RunSummary {
  run_id: string
  task_id: string
  task_title: string | null
  workflow: string | null
  state: RunState
  branch: string
  started_at: string
  ended_at: string | null
  duration_s: number | null
  tokens: number
  cost: number
  error: string | null
  note: string | null
  /** Archived: listed only in the archived view (absent from an older server). */
  archived?: boolean
  /** Who started the run: manual, auto-continue, auto-resolve; null before it was recorded. */
  started_by?: string | null
  /** A running run's pause: 'pausing' or 'paused'; null without one (absent from an older server). */
  pause?: RunPause | null
  /** Why a succeeded run has no PR (push or hosting failed); `task publish` retries. */
  pr_error?: string | null
  pr: RunPr | null
  phases: PhaseDot[]
}

export interface CostTotal {
  cost: number
  tokens: number
  runs: number
}

export interface TaskCostTotal extends CostTotal {
  task_id: string
  task_title: string | null
}

export interface RunTotals {
  backlog: CostTotal
  tasks: TaskCostTotal[]
}

export interface RunsResponse {
  runs: RunSummary[]
}

export interface Session {
  adw_id: string
  adw_name: string | null
  request: string | null
  status: string | null
  engineer: string | null
  started_at: string | null
  ended_at: string | null
  total_tokens: number | null
  total_cost: number | null
}

export interface UsageBreakdown {
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens?: number
  total_tokens: number
  input_cost: number
  output_cost: number
  cache_read_cost: number
  cache_write_cost: number
  total_cost: number
}

export interface PhaseRow {
  rowid?: number
  phase_id: string
  adw_id: string
  seq: number | null
  name: string | null
  kind: string | null
  owner: string | null
  description: string | null
  status: string | null
  attempt: number | null
  retries: number | null
  error: string | null
  started_at: string | null
  ended_at: string | null
  harness: string | null
  model: string | null
  tokens: number
  cost: number
  usage: Partial<UsageBreakdown> | null
  slot_wait?: SlotWait | null
  duration_s: number | null
}

export interface GateCheck {
  item: string
  ok: boolean
  note: string
}

export interface GateResult {
  id: number
  adw_id: string
  phase_id: string | null
  attempt: number | null
  gate: string | null
  passed: boolean
  violations: string[]
  checks: GateCheck[] | null
  created_at: string | null
}

export interface TraceEnvelope {
  rowid?: number
  envelope_id: string
  adw_id: string
  phase_id: string | null
  agent: string | null
  output_type: string | null
  payload: unknown
  payload_raw: string | null
  valid: boolean
  attempt: number | null
  created_at: string | null
}

export interface AgentSession {
  agent: string
  coding_agent: string | null
  model: string | null
  session_id: string | null
  color?: string | null
  context_tokens?: number | null
  context_window?: number | null
  created_at: string | null
  last_used_at: string | null
}

export interface RunDetail {
  run: RunSummary
  session: Session | null
  usage: { read: number; written: number }
  agents: AgentSession[]
  phases: PhaseRow[]
  gates: GateResult[]
  envelopes: TraceEnvelope[]
  /** Rowid cursors for /tail (absent from an older server). */
  cursors?: RunCursors
}

/** The newest rowid the client has of each trace table of a run. */
export interface RunCursors {
  events: number
  phases: number
  gates: number
  envelopes: number
}

/** GET /api/runs/{id}/tail: only what is new since the cursors. */
export interface RunTail {
  run: RunSummary
  session: Session | null
  events: TraceEvent[]
  phases: PhaseRow[]
  gates: GateResult[]
  envelopes: TraceEnvelope[]
  agents: AgentSession[]
  usage_delta: { read: number; written: number }
  cursors: RunCursors
  has_more: boolean
}

export interface TraceEvent {
  rowid: number
  event_id: string
  adw_id: string
  phase_id: string | null
  parent_id: string | null
  type: string | null
  name: string | null
  payload: unknown
  tokens: number | null
  started_at: string | null
  ended_at: string | null
}

export interface EventsPage {
  events: TraceEvent[]
  cursor: number
  has_more: boolean
}

export interface ToolCallPayload {
  tool?: string
  tool_call_id?: string
  args?: Record<string, unknown>
  result_snippet?: string
  ok?: boolean
  duration_ms?: number
  agent?: string
}

export interface AgentStartPayload {
  model?: string
  thinking?: string
  session_id?: string
  coding_agent?: string
  color?: string
  purpose?: string
  /** null = every tool; undefined = not recorded. */
  tools?: string[] | null
  harness_engineering?: string[]
}

export interface AgentEndPayload {
  cost?: number
  usage?: Partial<UsageBreakdown>
  context_tokens?: number
  context_window?: number
}

/** Payload of a `quality:<name>` tool_call event (engine/quality.py). */
export interface QualityPayload {
  command: string
  returncode?: number | null
  passed?: boolean
  area?: string
  operation?: string
  timeout_seconds?: number | null
  output_artifact?: string | null
}

/** GET /api/runs/{id}/phases/{phase}/prompts: the prompts one phase sent. */
export interface PhasePrompts {
  run_id: string
  phase_id: string
  phase: string | null
  agent: string | null
  kind: string | null
  /** "phase" = the phase's own prompts; "agent" = the agent's last prompts (legacy run). */
  source: 'phase' | 'agent' | 'none'
  legacy: boolean
  system: string | null
  user: string | null
  truncated: { system: boolean; user: boolean }
  max_bytes: number
}

export interface StopResponse {
  run: RunSummary
  signalled: number[]
  killed: number[]
}

/** `archived`: the archived runs instead of the active (not archived) ones. */
export function fetchRuns(archived = false): Promise<RunsResponse> {
  return getApi<RunsResponse>(archived ? '/runs?archived=1' : '/runs')
}

/** Cost totals over every run; the Runs page asks for them when its costs section opens. */
export function fetchRunTotals(): Promise<RunTotals> {
  return getApi<RunTotals>('/runs/totals')
}

export function fetchRun(runId: string): Promise<RunDetail> {
  return getApi<RunDetail>(`/runs/${encodeURIComponent(runId)}`)
}

/** Every trace event of a run, page by page. */
export async function fetchAllEvents(runId: string): Promise<TraceEvent[]> {
  const events: TraceEvent[] = []
  let after = 0
  for (;;) {
    const page = await getApi<EventsPage>(
      `/runs/${encodeURIComponent(runId)}/events?after=${after}&limit=1000`,
    )
    events.push(...(page.events ?? []))
    if (!page.has_more || page.cursor <= after) return events
    after = page.cursor
  }
}

/** What is new in a run since `cursors`; `openPhases` are phases shown as running. */
export function fetchRunTail(
  runId: string,
  cursors: RunCursors,
  openPhases: string[] = [],
): Promise<RunTail> {
  const query = new URLSearchParams({
    events: String(cursors.events),
    phases: String(cursors.phases),
    gates: String(cursors.gates),
    envelopes: String(cursors.envelopes),
    limit: '1000',
  })
  if (openPhases.length) query.set('open', openPhases.join(','))
  return getApi<RunTail>(`/runs/${encodeURIComponent(runId)}/tail?${query.toString()}`)
}

/** Cursors of a loaded run: from the detail, or from its rows when the server sent none. */
export function cursorsOf(detail: RunDetail, events: TraceEvent[]): RunCursors {
  if (detail.cursors) return { ...detail.cursors }
  const max = (values: (number | undefined)[]) =>
    values.reduce<number>((m, v) => (typeof v === 'number' && v > m ? v : m), 0)
  return {
    events: max(events.map((e) => e.rowid)),
    phases: max(detail.phases.map((p) => p.rowid)),
    gates: max(detail.gates.map((g) => g.id)),
    envelopes: max(detail.envelopes.map((e) => e.rowid)),
  }
}

/** Phases in seq order, ties by rowid. */
export function bySeq(a: PhaseRow, b: PhaseRow): number {
  const sa = a.seq ?? Number.MAX_SAFE_INTEGER
  const sb = b.seq ?? Number.MAX_SAFE_INTEGER
  return sa !== sb ? sa - sb : (a.rowid ?? 0) - (b.rowid ?? 0)
}

/** Merge a tail into a loaded run: phases by id, the rest appended without duplicates. */
export function applyTail(
  detail: RunDetail,
  events: TraceEvent[],
  tail: RunTail,
): { detail: RunDetail; events: TraceEvent[] } {
  const phases = new Map(detail.phases.map((p) => [p.phase_id, p]))
  for (const p of tail.phases) phases.set(p.phase_id, p)
  const gateIds = new Set(detail.gates.map((g) => g.id))
  const envelopeIds = new Set(detail.envelopes.map((e) => e.envelope_id))
  const rowids = new Set(events.map((e) => e.rowid))
  const newEvents = tail.events.filter((e) => !rowids.has(e.rowid))
  const delta = tail.usage_delta ?? { read: 0, written: 0 }
  return {
    detail: {
      ...detail,
      run: tail.run ?? detail.run,
      session: tail.session,
      agents: tail.agents ?? detail.agents,
      usage: {
        read: detail.usage.read + delta.read,
        written: detail.usage.written + delta.written,
      },
      phases: [...phases.values()].sort(bySeq),
      gates: [...detail.gates, ...tail.gates.filter((g) => !gateIds.has(g.id))],
      envelopes: [
        ...detail.envelopes,
        ...tail.envelopes.filter((e) => !envelopeIds.has(e.envelope_id)),
      ],
      cursors: { ...tail.cursors },
    },
    events: newEvents.length ? [...events, ...newEvents] : events,
  }
}

/** The system and user prompt of one phase, fetched once when the phase is opened. */
export function fetchPhasePrompts(runId: string, phaseId: string): Promise<PhasePrompts> {
  return getApi<PhasePrompts>(
    `/runs/${encodeURIComponent(runId)}/phases/${encodeURIComponent(phaseId)}/prompts`,
  )
}

/** Collapsed gate-row label: "k z N selhalo" when items failed, else the count. */
export function checksLabel(checks: GateCheck[]): string {
  const failed = checks.filter((c) => !c.ok).length
  return failed > 0 ? `${failed} z ${checks.length} selhalo` : String(checks.length)
}

export function stopRun(runId: string): Promise<StopResponse> {
  return postApi<StopResponse>(`/runs/${encodeURIComponent(runId)}/stop`)
}

export interface PauseResponse {
  run: RunSummary
}

/** Ask a running run to pause before its next phase (`factory task pause`). */
export function pauseRun(runId: string): Promise<PauseResponse> {
  return postApi<PauseResponse>(`/runs/${encodeURIComponent(runId)}/pause`)
}

/** Let a paused run go on with its next phase (`factory task resume`). */
export function resumeRun(runId: string): Promise<PauseResponse> {
  return postApi<PauseResponse>(`/runs/${encodeURIComponent(runId)}/resume`)
}

const STARTED_BY: Record<string, string> = {
  manual: 'ručně',
  'auto-continue': 'auto-continue',
  'auto-resolve': 'auto-resolve',
}

/** Who started a run, for the list and the detail: `ručně`, `auto-continue`, `auto-resolve`. */
export function startedByLabel(value: string | null | undefined): string {
  return value ? (STARTED_BY[value] ?? value) : '—'
}

/** Tooltip of who started a run. */
export function startedByTip(value: string | null | undefined): string {
  switch (value) {
    case 'manual':
      return 'Spuštěno ručně (dashboard nebo factory task run)'
    case 'auto-continue':
      return 'Spuštěno automaticky řetězem auto-continue'
    case 'auto-resolve':
      return 'Spuštěno automaticky: auto-merge řeší konflikt PR'
    default:
      return 'Neznámé: běh je starší než záznam o spuštění'
  }
}

/** A run that is no longer running: it can be archived. */
export function isFinished(run: RunSummary): boolean {
  return run.state !== 'running'
}

function runPath(runId: string, action: string): string {
  return `/runs/${encodeURIComponent(runId)}/${action}`
}

export interface PublishResponse {
  run: RunSummary
  pr: { url: string; pr_id: string; state: string } | null
  /** The push or the PR failed again. */
  pr_error: string | null
}

/** `factory task publish` for a succeeded run without a PR: push its branch, open the PR. */
export function publishRun(runId: string): Promise<PublishResponse> {
  return postApi<PublishResponse>(runPath(runId, 'publish'))
}

/** A succeeded run without a PR: the dashboard offers to publish it. */
export function canPublish(run: RunSummary): boolean {
  return run.state === 'succeeded' && !run.pr
}

/** Archive one finished run. */
export function archiveRun(runId: string): Promise<{ run: RunSummary }> {
  return postApi<{ run: RunSummary }>(runPath(runId, 'archive'))
}

/** Return one archived run to the active ones. */
export function unarchiveRun(runId: string): Promise<{ run: RunSummary }> {
  return postApi<{ run: RunSummary }>(runPath(runId, 'unarchive'))
}

/** Erase one archived run and its trace from the database. */
export function deleteRun(runId: string): Promise<{ deleted: string[] }> {
  return postApi<{ deleted: string[] }>(runPath(runId, 'delete'))
}

/** Archive every finished run (succeeded, failed, aborted, stopped). */
export function archiveFinishedRuns(): Promise<{ archived: string[] }> {
  return postApi<{ archived: string[] }>('/runs/archive-finished')
}

/** Erase every archived run and its trace from the database. */
export function deleteArchivedRuns(): Promise<{ deleted: string[] }> {
  return postApi<{ deleted: string[] }>('/runs/delete-archived')
}

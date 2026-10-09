// Shared fixtures for the Runs screen tests (same shapes as /api/runs).
import type { PhasePrompts, RunDetail, RunSummary, RunsResponse, RunTotals, TraceEvent } from '@/lib/runs'

export function summary(over: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: 'r-ok',
    task_id: 'M01-S01-T01',
    task_title: 'Schema',
    workflow: 'plan-commit',
    state: 'succeeded',
    branch: 'factory/M01-S01-T01-1',
    started_at: '2026-01-01T10:00:00+00:00',
    ended_at: '2026-01-01T10:05:00+00:00',
    duration_s: 300,
    tokens: 1180,
    cost: 0.25,
    error: null,
    note: null,
    started_by: 'manual',
    pr: { url: 'https://example.test/pr/7', pr_id: '7', state: 'open' },
    phases: [
      { seq: 1, name: 'plan', status: 'success' },
      { seq: 2, name: 'test', status: 'fail' },
    ],
    ...over,
  }
}

export function runsResponse(): RunsResponse {
  return {
    runs: [
      summary({ run_id: 'r-run', task_id: 'M01-S01-T02', task_title: 'Loader', state: 'running', pr: null, tokens: 100, cost: 0.01, started_by: 'auto-continue' }),
      summary(),
    ],
  }
}

export function runTotals(): RunTotals {
  return {
    backlog: { cost: 0.26, tokens: 1280, runs: 2 },
    tasks: [
      { task_id: 'M01-S01-T01', task_title: 'Schema', cost: 0.25, tokens: 1180, runs: 1 },
      { task_id: 'M01-S01-T02', task_title: 'Loader', cost: 0.01, tokens: 100, runs: 1 },
    ],
  }
}

export function detail(over: Partial<RunSummary> = {}): RunDetail {
  const phase = {
    adw_id: 'r-ok',
    description: null,
    attempt: 1,
    retries: 0,
    error: null,
    started_at: '2026-01-01T10:00:00+00:00',
    ended_at: '2026-01-01T10:03:00+00:00',
    duration_s: 180,
  }
  return {
    run: summary(over),
    session: {
      adw_id: 'r-ok',
      adw_name: null,
      request: '# Zadání\n\nNavrhnout **schéma**.',
      status: null,
      engineer: null,
      started_at: null,
      ended_at: null,
      total_tokens: null,
      total_cost: null,
    },
    usage: { read: 150, written: 30 },
    agents: [],
    // Out of order on purpose: the detail sorts by seq.
    phases: [
      { ...phase, phase_id: 'p2', seq: 2, name: 'test', kind: 'code', owner: 'tests', status: 'fail', harness: null, model: null, tokens: 0, cost: 0, usage: null },
      {
        ...phase,
        phase_id: 'p1',
        seq: 1,
        name: 'plan',
        kind: 'agent',
        owner: 'planner',
        description: 'Naplánuj práci',
        retries: 2,
        status: 'success',
        harness: 'claude',
        model: 'claude-opus',
        tokens: 1180,
        cost: 0.25,
        usage: {
          input_tokens: 100,
          output_tokens: 30,
          reasoning_tokens: 10,
          cache_read_tokens: 1000,
          cache_write_tokens: 50,
          total_tokens: 1180,
          input_cost: 0.1,
          output_cost: 0.1,
          cache_read_cost: 0.03,
          cache_write_cost: 0.02,
          total_cost: 0.25,
        },
      },
    ],
    gates: [
      { id: 1, adw_id: 'r-ok', phase_id: 'p1', attempt: 1, gate: 'artifacts_exist', passed: true, violations: [], checks: [{ item: 'specs/x.md', ok: true, note: 'exists' }], created_at: null },
      { id: 2, adw_id: 'r-ok', phase_id: 'p1', attempt: 2, gate: 'tests_pass', passed: false, violations: ['tests failed'], checks: [{ item: 'uv run pytest', ok: false, note: 'exit 1\nFAILED test_x' }, { item: 'ruff', ok: true, note: 'clean' }], created_at: '2026-01-01T10:02:00+00:00' },
    ],
    envelopes: [
      { envelope_id: 'env1', adw_id: 'r-ok', phase_id: 'p1', agent: 'planner', output_type: 'PlanOutput', payload: { status: 'success', summary: 'a plan' }, payload_raw: null, valid: true, attempt: 1, created_at: null },
    ],
  }
}

export function events(): TraceEvent[] {
  const base = { adw_id: 'r-ok', parent_id: null, tokens: null, started_at: '2026-01-01T10:01:00+00:00', ended_at: null }
  return [
    { ...base, rowid: 1, event_id: 'e1', phase_id: 'p1', type: 'agent_start', name: 'planner', payload: { coding_agent: 'claude', model: 'claude-opus-4', thinking: 'high', tools: ['Read', 'Edit'], harness_engineering: [], purpose: 'plánuje', session_id: 'sess-1' } },
    { ...base, rowid: 2, event_id: 'e2', phase_id: 'p1', type: 'tool_call', name: 'Read', payload: { tool: 'Read', args: { file_path: 'src/app/x.py' }, result_snippet: "print('x')", ok: true } },
    { ...base, rowid: 3, event_id: 'e3', phase_id: 'p2', type: 'phase_start', name: 'test', payload: {} },
  ]
}

/** More events of the run for the phase panel: agent_end, a quality check, a payload event. */
export function moreEvents(): TraceEvent[] {
  const base = { adw_id: 'r-ok', parent_id: null, tokens: null, started_at: '2026-01-01T10:02:00+00:00', ended_at: '2026-01-01T10:02:03+00:00' }
  return [
    { ...base, rowid: 4, event_id: 'e4', phase_id: 'p1', type: 'agent_end', name: 'planner', tokens: 1180, payload: { cost: 0.25, usage: { input_tokens: 100, output_tokens: 30 } } },
    { ...base, rowid: 5, event_id: 'e5', phase_id: 'p2', type: 'tool_call', name: 'quality:test', payload: { area: 'test', command: 'uv run pytest', returncode: 1, passed: false } },
    { ...base, rowid: 6, event_id: 'e6', phase_id: 'p2', type: 'phase_end', name: 'test', payload: { status: 'fail' } },
  ]
}

/** A /prompts answer of phase p1. */
export function prompts(over: Partial<PhasePrompts> = {}): PhasePrompts {
  return {
    run_id: 'r-ok',
    phase_id: 'p1',
    phase: 'plan',
    agent: 'planner',
    kind: 'agent',
    source: 'phase',
    legacy: false,
    system: 'You are the planner.\nPlan **well**.\nThird line.',
    user: 'Zadání prvního tasku.',
    truncated: { system: false, user: false },
    max_bytes: 262144,
    ...over,
  }
}

/** The API envelope around `data`, as a fetch Response. */
export function okResponse(data: unknown): Response {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

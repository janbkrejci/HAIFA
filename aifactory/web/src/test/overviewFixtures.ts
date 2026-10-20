// Shared fixtures for the overview tests (same shapes as GET /api/overview).
import type {
  OverviewConfig,
  OverviewData,
  OverviewFactory,
  OverviewFailed,
  OverviewMergedOutside,
  OverviewRepo,
  OverviewReview,
  OverviewRunning,
} from '@/lib/api'

export function config(over: Partial<OverviewConfig> = {}): OverviewConfig {
  return {
    factory_state: 'installed',
    installed: true,
    base: 'main',
    commit: 'abc123',
    invalid: false,
    issues: [],
    uncommitted: [],
    clean: true,
    ...over,
  }
}

export function running(over: Partial<OverviewRunning> = {}): OverviewRunning {
  return {
    run_id: 'run-1',
    operation_id: null,
    task_id: 'M01-S01-T01',
    task_title: 'Schema',
    workflow: 'build-test-review',
    started_at: '2026-10-06T10:00:00+00:00',
    phase: { name: 'build', attempt: 2, started_at: '2026-10-06T10:01:00+00:00' },
    cost: 1.25,
    tokens: 1000,
    process: 'alive',
    status_label: null,
    pause: null,
    ...over,
  }
}

export function operation(id: string, over: Partial<OverviewRunning> = {}): OverviewRunning {
  return running({ run_id: null, operation_id: id, workflow: 'run', phase: null, cost: 0, tokens: 0, ...over })
}

export function review(over: Partial<OverviewReview> = {}): OverviewReview {
  return {
    task_id: 'M01-S01-T02',
    task_title: 'API',
    pr_id: '42',
    url: 'https://example.test/pr/42',
    branch: 'factory/M01-S01-T02-1',
    opened_at: '2026-10-06T09:00:00+00:00',
    age_s: 3600,
    source: 'trace',
    ...over,
  }
}

export function failed(over: Partial<OverviewFailed> = {}): OverviewFailed {
  return {
    run_id: 'run-f',
    task_id: 'M01-S01-T03',
    task_title: 'UI',
    state: 'failed',
    workflow: 'build-test-review',
    ended_at: '2026-10-06T08:00:00+00:00',
    error: 'tests failed',
    ...over,
  }
}

export function mergedOutside(over: Partial<OverviewMergedOutside> = {}): OverviewMergedOutside {
  return {
    task_id: 'M01-S01-T04',
    task_title: 'Merged by hand',
    pr_id: '37',
    url: 'https://example.test/pr/37',
    branch: 'factory/M01-S01-T04-1',
    merged_at: '2026-10-06T09:00:00+00:00',
    ...over,
  }
}

export function repo(id: string, over: Partial<OverviewRepo> = {}): OverviewRepo {
  return {
    id,
    name: id,
    path: `/work/${id}`,
    state: 'ok',
    has_trace: true,
    running: [],
    review: [],
    automerge: [],
    failed: [],
    config: config(),
    last_activity: '2026-10-06T10:00:00+00:00',
    warnings: [],
    tasks: null,
    factory: null,
    ...over,
  }
}

export function factory(over: Partial<OverviewFactory> = {}): OverviewFactory {
  return {
    max_parallel_runs: 2,
    running: 0,
    free_slots: 2,
    ready: 0,
    can_start: false,
    paused: 0,
    pausing: 0,
    control: null,
    ...over,
  }
}

export function tasks(over: Partial<NonNullable<OverviewRepo['tasks']>> = {}): NonNullable<OverviewRepo['tasks']> {
  return { todo: 0, ready: 0, human: 0, blocked: 0, running: 0, 'in review': 0, 'awaiting merge': 0, done: 0, cancelled: 0, ...over }
}

export function overview(repos: OverviewRepo[]): OverviewData {
  return { repos, totals: {} }
}

// Shared fixtures for the overview tests (same shapes as GET /api/overview).
import type {
  OverviewConfig,
  OverviewData,
  OverviewFailed,
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
    task_id: 'M01-S01-T01',
    task_title: 'Schema',
    workflow: 'build-test-review',
    started_at: '2026-10-06T10:00:00+00:00',
    phase: { name: 'build', attempt: 2, started_at: '2026-10-06T10:01:00+00:00' },
    cost: 1.25,
    tokens: 1000,
    process: 'alive',
    status_label: null,
    ...over,
  }
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

export function repo(id: string, over: Partial<OverviewRepo> = {}): OverviewRepo {
  return {
    id,
    name: id,
    path: `/work/${id}`,
    state: 'ok',
    has_trace: true,
    running: [],
    review: [],
    failed: [],
    config: config(),
    last_activity: '2026-10-06T10:00:00+00:00',
    warnings: [],
    ...over,
  }
}

export function overview(repos: OverviewRepo[]): OverviewData {
  return { repos, totals: {} }
}

// Shared fixtures for the Review screen tests (same shapes as /api/review).
import type { ReviewDetail, ReviewDonePr, ReviewList, ReviewPr, TaskPr } from '@/lib/review'

export const APPROVE_NOTE =
  'Schválení zatím neposílá approve review v hostingu (OB3): rovnou přidá commit se status: done a PR merguje.'

export function taskPr(over: Partial<TaskPr> = {}): TaskPr {
  return {
    branch: 'factory/M01-S01-T01-1',
    task_id: 'M01-S01-T01',
    provider: 'github',
    pr_id: '7',
    url: 'https://example.test/pr/7',
    base: 'main',
    base_sha: 'aaaaaaa1',
    title: 'M01-S01-T01: Schema',
    state: 'open',
    created_at: '2026-01-01T10:05:00+00:00',
    updated_at: '2026-01-01T10:05:00+00:00',
    merged_at: null,
    merge_sha: null,
    ...over,
  }
}

export function reviewPr(over: Partial<ReviewPr> = {}): ReviewPr {
  return {
    task_id: 'M01-S01-T01',
    task_title: 'Schema',
    project_id: 'M01',
    pr: taskPr(),
    provider_state: 'open',
    mergeability: 'mergeable',
    running_run: null,
    awaiting_review: true,
    cost: 0.25,
    tokens: 1180,
    runs: 1,
    last_run: { run_id: 'r-ok', state: 'succeeded', workflow: 'plan-commit', ended_at: null },
    ...over,
  }
}

export function donePr(over: Partial<ReviewDonePr> = {}): ReviewDonePr {
  return {
    task_id: 'M03-S01-T01',
    task_title: 'Export',
    project_id: 'M03',
    provider_state: 'merged',
    done_at: '2026-01-02T09:00:00+00:00',
    cost: 0.5,
    tokens: 2000,
    pr: taskPr({
      task_id: 'M03-S01-T01',
      branch: 'factory/M03-S01-T01-1',
      pr_id: '9',
      url: 'https://example.test/pr/9',
      state: 'merged',
      merged_at: '2026-01-02T09:00:00+00:00',
      merge_sha: 'bbbbbbb2',
    }),
    ...over,
  }
}

export function reviewList(over: Partial<ReviewList> = {}): ReviewList {
  return {
    prs: [
      reviewPr(),
      reviewPr({
        task_id: 'M02-S01-T01',
        task_title: 'Loader',
        project_id: 'M02',
        pr: taskPr({ task_id: 'M02-S01-T01', pr_id: 'factory/M02-S01-T01-1', url: 'local:factory/M02-S01-T01-1', branch: 'factory/M02-S01-T01-1' }),
        mergeability: 'conflict',
        running_run: { run_id: 'r-run', workflow: 'resolve', started_at: '2026-01-01T11:00:00+00:00' },
        awaiting_review: false,
        cost: 1.5,
        tokens: 20000,
      }),
    ],
    provider: 'github',
    levels: ['module', 'step', 'task'],
    approve_review_sent: false,
    approve_note: APPROVE_NOTE,
    ...over,
  }
}

const PATCH = [
  'diff --git a/specs/x.md b/specs/x.md',
  'new file mode 100644',
  'index 0000000..1111111',
  '--- /dev/null',
  '+++ b/specs/x.md',
  '@@ -0,0 +1,2 @@',
  '+# spec',
  '+body',
  '',
].join('\n')

export function reviewDetail(over: Partial<ReviewDetail> = {}): ReviewDetail {
  return {
    task_id: 'M01-S01-T01',
    task_title: 'Schema',
    project_id: 'M01',
    pr: taskPr({ body: '## Zadání\n\nNapiš schema.' }),
    provider_state: 'open',
    mergeability: 'mergeable',
    running_run: null,
    awaiting_review: true,
    cost: 0.25,
    tokens: 1180,
    runs: [
      { run_id: 'r-ok', workflow: 'plan-commit', state: 'succeeded', started_at: '2026-01-01T10:00:00+00:00', ended_at: '2026-01-01T10:05:00+00:00', note: null, error: null, cost: 0.25, tokens: 1180 },
    ],
    diff: {
      base: 'main',
      merge_base: 'aaaaaaa1',
      stat: { files: 2, additions: 3, deletions: 1 },
      files: [
        { path: 'specs/x.md', old_path: null, status: 'added', additions: 2, deletions: 0, binary: false, patch: PATCH, truncated: false },
        { path: 'img/logo.png', old_path: null, status: 'modified', additions: 0, deletions: 0, binary: true, patch: '', truncated: false },
      ],
    },
    checks: [
      { kind: 'gate', name: 'artifacts_exist', phase: 'plan', passed: true, detail: 'ok', run_id: 'r-ok' },
      { kind: 'test', name: 'pytest', phase: 'test', passed: false, detail: '1 failed', run_id: 'r-ok' },
    ],
    review: {
      approved: false,
      summary: 'Chybí test.',
      blocking: ['přidej test loaderu'],
      findings: [{ requirement: 'Loader čte YAML', met: true, evidence: 'src/loader.py' }],
      agent: 'reviewer',
      run_id: 'r-ok',
      created_at: '2026-01-01T10:04:00+00:00',
    },
    actions: { approve: true, return: true, resolve: true },
    approve_review_sent: false,
    approve_note: APPROVE_NOTE,
    ...over,
  }
}

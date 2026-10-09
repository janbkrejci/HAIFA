// Open task PRs and their review, as served by /api/review (aifactory/web/review.py).
// Approve, return and resolve call the same core functions as `factory task approve|return|resolve`.
import { getApi, postApi } from './api'

export type Mergeability = 'mergeable' | 'conflict' | 'unknown'
export type ProviderState = 'open' | 'merged' | 'closed'

export interface TaskPr {
  branch: string
  task_id: string
  provider: string
  pr_id: string
  url: string
  base: string
  base_sha: string
  title: string
  body?: string
  state: string
  created_at: string
  updated_at: string
  merged_at: string | null
  merge_sha: string | null
  /** Who merged the PR: 'auto-merge' or 'operator' (null: not merged by factory). */
  merged_by?: string | null
  /** Why auto-merge left the PR open ("<code>: <reason>"). */
  auto_merge_error?: string | null
}

/** The PR was merged by auto-merge, not by the operator. */
export function mergedByAuto(pr: { merged_by?: string | null } | null | undefined): boolean {
  return pr?.merged_by === 'auto-merge'
}

export interface RunningRun {
  run_id: string
  workflow: string | null
  started_at: string
}

export interface LastRun {
  run_id: string
  state: string
  workflow: string | null
  ended_at: string | null
}

interface ReviewBase {
  task_id: string
  task_title: string | null
  /** The project (top level of `levels`) of the task. */
  project_id: string | null
  pr: TaskPr
  provider_state: ProviderState | null
  mergeability: Mergeability
  running_run: RunningRun | null
  awaiting_review: boolean
  cost: number
  tokens: number
}

/** One item of GET /api/review. */
export interface ReviewPr extends ReviewBase {
  runs: number
  last_run: LastRun | null
}

/** One item of `done` in GET /api/review?done=1: a merged or closed task PR. */
export interface ReviewDonePr {
  task_id: string
  task_title: string | null
  /** The project (top level of `levels`) of the task. */
  project_id: string | null
  provider_state: 'merged' | 'closed'
  done_at: string
  cost: number
  tokens: number
  pr: TaskPr
}

export interface ReviewList {
  prs: ReviewPr[]
  /** Only with `fetchReviews({ done: true })`. */
  done?: ReviewDonePr[]
  provider: string
  /** `levels` of the backlog; the first one names the project column. */
  levels?: string[]
  approve_review_sent: boolean
  approve_note: string
}

export type DiffStatus = 'added' | 'modified' | 'deleted' | 'renamed'

export interface DiffFile {
  path: string
  old_path: string | null
  status: DiffStatus
  additions: number
  deletions: number
  binary: boolean
  patch: string
  truncated: boolean
}

export interface ReviewDiff {
  base: string
  merge_base: string | null
  stat: { files: number; additions: number; deletions: number }
  files: DiffFile[]
}

export interface CheckResult {
  kind: 'gate' | 'test' | string
  name: string
  phase: string
  passed: boolean
  detail: string
  run_id: string
}

export interface ReviewFinding {
  requirement?: string
  met?: boolean
  evidence?: string
}

export interface ReviewVerdict {
  approved: boolean
  summary: string
  blocking: string[]
  findings: ReviewFinding[]
  agent: string | null
  run_id: string
  created_at: string | null
}

export interface ReviewRun {
  run_id: string
  workflow: string | null
  state: string
  started_at: string
  ended_at: string | null
  note: string | null
  error: string | null
  cost: number
  tokens: number
}

export interface ReviewActions {
  approve: boolean
  return: boolean
  resolve: boolean
}

/** GET /api/review/<task_id>. */
export interface ReviewDetail extends ReviewBase {
  runs: ReviewRun[]
  diff: ReviewDiff
  checks: CheckResult[]
  review: ReviewVerdict | null
  actions: ReviewActions
  /** `levels` of the backlog; the first one names the project. */
  levels?: string[]
  approve_review_sent: boolean
  approve_note: string
}

export interface ApproveResult {
  ok: boolean
  task_id: string
  pr: TaskPr
  merge_sha: string | null
  merged_by?: string
  strategy: string
  reviewed: boolean
  approve_review_sent: boolean
  approve_note: string
}

/** A review action whose button shows the spinner. */
export type ReviewAction = 'approve' | 'return' | 'resolve'

export interface ActionStarted {
  task_id: string
  action: 'return' | 'resolve'
  run: { run_id: string; workflow: string | null; branch: string } | null
  pending: boolean
}

export function fetchReviews(opts: { done?: boolean } = {}): Promise<ReviewList> {
  return getApi<ReviewList>(opts.done ? '/review?done=1' : '/review')
}

/** localStorage key of the "Zobrazit hotové" choice ('1' or '0'). */
export const SHOW_DONE_KEY = 'haifa.review.showDone'

export function loadShowDone(): boolean {
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem(SHOW_DONE_KEY) === '1'
  } catch {
    return false
  }
}

export function saveShowDone(value: boolean): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(SHOW_DONE_KEY, value ? '1' : '0')
  } catch {
    // storage unavailable: the choice lasts for this visit only
  }
}

/** Czech label of a done PR's state. */
export function doneLabel(state: string | null | undefined): string {
  if (state === 'merged') return 'sloučeno'
  if (state === 'closed') return 'zavřeno'
  return state ?? '—'
}

function isDone(state: string | null | undefined): boolean {
  return state === 'merged' || state === 'closed'
}

/** A merged or closed PR: its detail offers no actions. */
export function isReadOnly(detail: { provider_state: string | null; pr: { state: string } }): boolean {
  return isDone(detail.provider_state) || isDone(detail.pr?.state)
}

export function fetchReview(taskId: string): Promise<ReviewDetail> {
  return getApi<ReviewDetail>(`/review/${encodeURIComponent(taskId)}`)
}

export function approvePr(taskId: string): Promise<ApproveResult> {
  return postApi<ApproveResult>(`/review/${encodeURIComponent(taskId)}/approve`)
}

export function returnPr(taskId: string, note: string): Promise<ActionStarted> {
  return postApi<ActionStarted>(`/review/${encodeURIComponent(taskId)}/return`, { note })
}

export function resolvePr(taskId: string): Promise<ActionStarted> {
  return postApi<ActionStarted>(`/review/${encodeURIComponent(taskId)}/resolve`, {})
}

export type DiffLineKind = 'add' | 'del' | 'hunk' | 'meta' | 'ctx'

export interface DiffLine {
  kind: DiffLineKind
  text: string
}

const META = /^(diff --git |index |--- |\+\+\+ |new file mode|deleted file mode|old mode|new mode|similarity index|dissimilarity index|rename from|rename to|copy from|copy to|Binary files|\\ No newline)/

/** The lines of a unified patch, classified for colouring. */
export function diffLines(patch: string): DiffLine[] {
  if (!patch) return []
  const lines = patch.replace(/\n$/, '').split('\n')
  let inHunk = false
  return lines.map((text) => {
    if (text.startsWith('@@')) {
      inHunk = true
      return { kind: 'hunk', text }
    }
    if (text.startsWith('diff --git ')) inHunk = false
    if (!inHunk && META.test(text)) return { kind: 'meta', text }
    if (text.startsWith('\\ No newline')) return { kind: 'meta', text }
    if (text.startsWith('+')) return { kind: 'add', text }
    if (text.startsWith('-')) return { kind: 'del', text }
    return { kind: 'ctx', text }
  })
}

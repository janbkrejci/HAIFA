// The Lekce section of the Factory screen (`/learn`): the lessons of `factory learn`, the scan
// that finds them (Najít lekce, optionally over the objections of every registered repo), and
// Přijmout (a backlog task) or Zamítnout of one lesson.
import { getApi, postApi } from './api'

export type LessonState = 'proposed' | 'accepted' | 'rejected'

export interface LessonComplaint {
  run_id: string
  task_id: string
  source: string
  phase: string
  text: string
  created_at: string
  /** The registry id of the repo the objection comes from ('' when unknown). */
  repo: string
}

export interface LessonCount {
  runs: number
  objections: number
}

export interface Lesson {
  id: string
  rule: string
  target: string
  target_detail: string
  state: LessonState
  reason: string | null
  task_id: string | null
  occurrences: number
  /** The registry ids of the repos the lesson's objections come from. */
  origin: string[]
  runs: { run_id: string; task_id: string; repo: string }[]
  complaints: LessonComplaint[]
  pr: { url: string; state: string; merged_at: string | null } | null
  effect: { merged_at: string; before: LessonCount; after: LessonCount } | null
}

export interface LessonScanResult {
  objections: number
  runs: number
  lessons: number
  repeats: number
  /** Only for a scan of every repo: the repos of the objections, the lessons saved in other
   * repos than this one by repo id, and what could not be read. */
  repos?: number
  elsewhere?: Record<string, number>
  warnings?: string[]
}

export interface LessonScan {
  state: 'running' | 'done' | 'failed'
  since: string | null
  /** The scan read the objections of every registered repo (`factory learn scan --all`). */
  all: boolean
  started_at: string
  finished_at: string | null
  result: LessonScanResult | null
  error: string | null
}

export interface LearnState {
  lessons: Lesson[]
  scan: LessonScan | null
}

export interface AcceptedLesson {
  id: string
  state: LessonState
  task: { id: string; title: string; path: string; step: string; workflow: string; writes: string[] }
  existed: boolean
  committed: boolean
}

export const SOURCE_TEXT: Record<string, string> = {
  review: 'review',
  test_review: 'review testů',
  test_triage: 'triáž testů',
  revise: 'oprava',
}

/** Where the rule of a lesson belongs, e.g. `AGENTS.md` or `skill release`. */
export function targetText(lesson: Pick<Lesson, 'target' | 'target_detail'>): string {
  return lesson.target_detail ? `${lesson.target} ${lesson.target_detail}` : lesson.target
}

export function fetchLearn(signal?: AbortSignal): Promise<LearnState> {
  return getApi<LearnState>('/learn', signal)
}

/** The lessons a scan of every repo saved in other repos, by repo id, sorted by id. */
export function lessonsElsewhere(result: LessonScanResult | null | undefined): [string, number][] {
  return Object.entries(result?.elsewhere ?? {})
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => a.localeCompare(b))
}

export function startLessonScan(options: { since?: string | null; all?: boolean } = {}): Promise<LessonScan> {
  const body: { since?: string; all?: boolean } = {}
  if (options.since) body.since = options.since
  if (options.all) body.all = true
  return postApi<LessonScan>('/learn/scan', body)
}

export function acceptLesson(id: string, project?: string | null): Promise<AcceptedLesson> {
  return postApi<AcceptedLesson>(`/learn/lessons/${encodeURIComponent(id)}/accept`, project ? { project } : {})
}

export function dismissLesson(id: string, reason?: string | null): Promise<{ id: string; state: LessonState }> {
  return postApi(`/learn/lessons/${encodeURIComponent(id)}/dismiss`, reason ? { reason } : {})
}

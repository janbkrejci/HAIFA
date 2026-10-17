// The Lekce section of the Factory screen (`/learn`): the lessons of `factory learn`, the scan
// that finds them (Najít lekce), and Přijmout (a backlog task) or Zamítnout of one lesson.
import { getApi, postApi } from './api'

export type LessonState = 'proposed' | 'accepted' | 'rejected'

export interface LessonComplaint {
  run_id: string
  task_id: string
  source: string
  phase: string
  text: string
  created_at: string
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
  runs: { run_id: string; task_id: string }[]
  complaints: LessonComplaint[]
  pr: { url: string; state: string; merged_at: string | null } | null
  effect: { merged_at: string; before: LessonCount; after: LessonCount } | null
}

export interface LessonScan {
  state: 'running' | 'done' | 'failed'
  since: string | null
  started_at: string
  finished_at: string | null
  result: { objections: number; runs: number; lessons: number; repeats: number } | null
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

export function startLessonScan(since?: string | null): Promise<LessonScan> {
  return postApi<LessonScan>('/learn/scan', since ? { since } : {})
}

export function acceptLesson(id: string, project?: string | null): Promise<AcceptedLesson> {
  return postApi<AcceptedLesson>(`/learn/lessons/${encodeURIComponent(id)}/accept`, project ? { project } : {})
}

export function dismissLesson(id: string, reason?: string | null): Promise<{ id: string; state: LessonState }> {
  return postApi(`/learn/lessons/${encodeURIComponent(id)}/dismiss`, reason ? { reason } : {})
}

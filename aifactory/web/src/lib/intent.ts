// The Nový záměr dialog of the Backlog (`/backlog/intent`): a proposer agent turns an intent
// into tasks and places them itself (an existing or new project, an existing or new step); the
// person refines, edits and applies it.
import { getApi, postApi, type ApiIssue } from './api'

export interface IntentTarget {
  project?: string | null
  step?: string | null
}

/** Where a job's latest proposal goes; null ids until there is one. */
export interface IntentPlacement extends IntentTarget {
  new_project?: boolean
  new_step?: boolean
}

export interface ProposalFinding {
  rule: string
  task: string
  message: string
  blocking: boolean
}

export interface ProposalTask {
  id: string
  code: string
  title: string
  body: string
  workflow: string
  writes: string[]
  depends_on: string[]
  path: string
}

export interface Proposal {
  summary: string
  applied: boolean
  /** The project of the step; null when the step is top level. */
  project?: { id: string; title: string; body: string; path: string; new: boolean } | null
  /** Why the agent placed the tasks there (empty for a requested target). */
  placement_reason?: string
  target?: IntentTarget
  step: { id: string; title: string; body: string; path: string; new: boolean }
  tasks: ProposalTask[]
  files: string[]
  findings: ProposalFinding[]
  commit?: { committed: boolean; commit: string | null; base: string } | null
  warnings?: string[]
}

export interface IntentProgress {
  kind: string
  text: string
  ts: string
}

export type IntentState = 'queued' | 'running' | 'ready' | 'failed' | 'applying' | 'applied' | 'closed'

export interface IntentJob {
  job_id: string
  state: IntentState
  round: number
  intent: string
  target: IntentPlacement
  requested?: IntentTarget
  proposal: Proposal | null
  error: string | null
  issues: ApiIssue[]
  notes: string[]
  progress: IntentProgress[]
  applied: { files: string[]; commit: Proposal['commit']; warnings: string[] } | null
}

/** What the person keeps of the proposal: the tasks by code, with their edited texts. */
export interface TaskEdit {
  code: string
  title: string
  body: string
}

export function isWorking(state: IntentState | undefined): boolean {
  return state === 'queued' || state === 'running'
}

/** Without a target the agent chooses the place. */
export function startIntent(intent: string, target: IntentTarget = {}): Promise<IntentJob> {
  return postApi<IntentJob>('/backlog/intent', { intent, ...target })
}

export function fetchIntent(job: string, signal?: AbortSignal): Promise<IntentJob> {
  return getApi<IntentJob>(`/backlog/intent/${encodeURIComponent(job)}`, signal)
}

export function refineIntent(job: string, note: string, tasks: TaskEdit[]): Promise<IntentJob> {
  return postApi<IntentJob>(`/backlog/intent/${encodeURIComponent(job)}/refine`, { note, tasks })
}

export function applyIntent(job: string, tasks: TaskEdit[]): Promise<Proposal> {
  return postApi<Proposal>(`/backlog/intent/${encodeURIComponent(job)}/apply`, { tasks })
}

export function discardIntent(job: string): Promise<unknown> {
  return postApi(`/backlog/intent/${encodeURIComponent(job)}/discard`)
}

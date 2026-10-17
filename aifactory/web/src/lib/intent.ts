// The Nový záměr dialog of the Backlog (`/backlog/intent`): a proposer agent turns an intent
// into a new step with tasks (or new tasks of a step); the person refines, edits and applies it.
import { getApi, postApi, type ApiIssue } from './api'

export interface IntentTarget {
  project?: string | null
  step?: string | null
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
  target: IntentTarget
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

export function startIntent(intent: string, target: IntentTarget): Promise<IntentJob> {
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

/** The value of the target menu, `project:<id>` or `step:<id>`, as a target. */
export function parseTarget(value: string): IntentTarget | null {
  const [kind, ...rest] = value.split(':')
  const id = rest.join(':')
  if (!id) return null
  if (kind === 'project') return { project: id }
  if (kind === 'step') return { step: id }
  return null
}

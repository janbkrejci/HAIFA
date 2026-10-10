// Settings screen: .factory/config.yaml (shared) and .factory/local.yaml (local), and the
// uncommitted config status (D4, `factory config status`).
import { getApi, postApi, type ApiIssue } from './api'
import { splitLines, type ContainerDetail } from './backlog'
import { toCommitStatus, type CommitStatus } from './commitStatus'

export interface SharedSettings {
  workdir: string
  backlog_dir: string
  specs_dir: string
  docs_dir: string
  worktrees_dir: string
  base: string
  git_provider: string
  merge_strategy: string
  protected_files: string[]
  max_parallel_runs: number | string
}

/** .factory/local.yaml; the dashboard port is in the registry (dashboard.yaml), not here. */
export interface LocalSettings {
  trace_db: string
}

export interface FileIssue {
  path: string
  message: string
}

/** `factory config status` (D4): shared config in `.factory/` not committed to base. */
export type ConfigStatus = CommitStatus

export interface SettingsData {
  projects?: ContainerDetail[]
  repository?: string
  shared: SharedSettings
  local: LocalSettings
  files: { shared: string; local: string }
  options: { git_provider: string[]; merge_strategy: string[] }
  shared_issues: FileIssue[]
  local_issues: FileIssue[]
  status: ConfigStatus | null
  saved?: string[]
}

export interface SettingsSaveInput {
  shared?: Partial<SharedSettings>
  local?: Partial<LocalSettings>
}

/** The editable form values: every field as text (protected_files one per line). */
export interface SettingsFormValues {
  workdir: string
  backlog_dir: string
  specs_dir: string
  docs_dir: string
  worktrees_dir: string
  base: string
  git_provider: string
  merge_strategy: string
  protected_files: string
  max_parallel_runs: string
  trace_db: string
}

export const SHARED_TEXT_FIELDS = [
  'workdir',
  'backlog_dir',
  'specs_dir',
  'docs_dir',
  'worktrees_dir',
  'base',
] as const

export function fetchSettings(): Promise<SettingsData> {
  return getApi<SettingsData>('/settings')
}

export function saveSettings(input: SettingsSaveInput): Promise<SettingsData> {
  return postApi<SettingsData>('/settings', input)
}

export async function fetchConfigStatus(): Promise<ConfigStatus | null> {
  return toCommitStatus(await getApi<unknown>('/config/status'))
}

/** Issues by field (`issue.id`); issues without a field go under ''. */
export function fieldErrors(issues: ApiIssue[]): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const issue of issues) {
    const key = issue.id ?? ''
    ;(out[key] ??= []).push(issue.message)
  }
  return out
}

export function formValues(data: SettingsData): SettingsFormValues {
  const s = data.shared
  return {
    workdir: s.workdir,
    backlog_dir: s.backlog_dir,
    specs_dir: s.specs_dir,
    docs_dir: s.docs_dir,
    worktrees_dir: s.worktrees_dir,
    base: s.base,
    git_provider: s.git_provider,
    merge_strategy: s.merge_strategy,
    protected_files: s.protected_files.join('\n'),
    max_parallel_runs: String(s.max_parallel_runs ?? 1),
    trace_db: data.local.trace_db,
  }
}

function sameList(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i])
}

/** A whole number as a number, anything else as the text (the server rejects it). */
function intValue(text: string): number | string {
  const trimmed = text.trim()
  return /^\d+$/.test(trimmed) ? Number(trimmed) : text
}

/** Only the changed values, shaped for POST /api/settings (sections without changes left out). */
export function settingsDiff(
  initial: SettingsFormValues,
  current: SettingsFormValues,
): SettingsSaveInput {
  const shared: Partial<SharedSettings> = {}
  for (const name of SHARED_TEXT_FIELDS) {
    if (current[name] !== initial[name]) shared[name] = current[name]
  }
  if (current.git_provider !== initial.git_provider) shared.git_provider = current.git_provider
  if (current.merge_strategy !== initial.merge_strategy) {
    shared.merge_strategy = current.merge_strategy
  }
  const protectedFiles = splitLines(current.protected_files)
  if (!sameList(protectedFiles, splitLines(initial.protected_files))) {
    shared.protected_files = protectedFiles
  }
  if (current.max_parallel_runs.trim() !== initial.max_parallel_runs.trim()) {
    shared.max_parallel_runs = intValue(current.max_parallel_runs)
  }

  const local: Partial<LocalSettings> = {}
  if (current.trace_db !== initial.trace_db) local.trace_db = current.trace_db

  const input: SettingsSaveInput = {}
  if (Object.keys(shared).length) input.shared = shared
  if (Object.keys(local).length) input.local = local
  return input
}

export function isEmptyInput(input: SettingsSaveInput): boolean {
  return !input.shared && !input.local
}

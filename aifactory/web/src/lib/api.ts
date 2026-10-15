// The dashboard API answers in the same envelope as `factory --json`. Repo endpoints live under
// /api/repos/<id> of the repo in the URL; health, the repo list, code and restart are global.
import type { BoardState } from './backlog'
import { currentRepoId } from './router'

/** One validation problem (`error.issues[i]`), e.g. a `backlog check` issue. */
export interface ApiIssue {
  code: string
  message: string
  path: string | null
  id: string | null
}

export interface ApiErrorBody {
  code: string
  message: string
  path: string | null
  id: string | null
  issues: Record<string, unknown>[]
}

export interface Envelope<T> {
  ok: boolean
  data: T | null
  error: ApiErrorBody | null
  warnings: string[]
}

export class ApiError extends Error {
  readonly code: string
  readonly issues: ApiIssue[]
  /** `data` of a failed envelope (e.g. the other repo of `trace_db_shared`), null without. */
  readonly data: unknown

  constructor(code: string, message: string, issues: ApiIssue[] = [], data: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.issues = issues
    this.data = data
  }
}

/** The trace DB stayed locked by other runs through the whole server-side wait. */
export const DB_BUSY_CODE = 'trace_db_locked'
/** What the dashboard says instead of a raw "database is locked". */
export const DB_BUSY_MESSAGE =
  'Databáze běhů je právě obsazená souběžnými běhy a ani po čekání se ji nepodařilo použít. Zkus to znovu za chvíli.'

/** True for an ApiError of a busy trace DB: the request may simply be tried again. */
export function isDbBusy(e: unknown): boolean {
  return e instanceof ApiError && e.code === DB_BUSY_CODE
}

/** True when an error text shown in the view is (or contains) the busy-DB message. */
export function isDbBusyText(text: string | null | undefined): boolean {
  return !!text && text.includes(DB_BUSY_MESSAGE)
}

/** The API prefix of the current repo (from the hash): `/api/repos/<id>`. */
export function apiBase(): string {
  const id = currentRepoId()
  if (id === null) throw new ApiError(NO_REPO_CODE, 'Není vybrané žádné repo')
  return `/api/repos/${encodeURIComponent(id)}`
}

/** No repo in the URL: a repo-scoped request is not sent at all. */
export const NO_REPO_CODE = 'no_repo'

function postInit(body?: unknown): RequestInit {
  const init: RequestInit = { method: 'POST' }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  return init
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  return readEnvelope<T>(await (init === undefined ? fetch(url) : fetch(url, init)))
}

/** GET /api/repos/<current repo><path>; returns `data` or throws ApiError with the envelope's error.code. */
export async function getApi<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(apiBase() + path, signal ? { signal } : undefined)
}

/** POST /api/repos/<current repo><path> with an optional JSON body; same envelope handling as getApi. */
export async function postApi<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(apiBase() + path, { ...postInit(body), ...(signal ? { signal } : {}) })
}

/** GET /api<path> of the dashboard itself (health, repos, code), not of a repo. */
export async function getGlobal<T>(path: string): Promise<T> {
  return request<T>(`/api${path}`)
}

/** POST /api<path> of the dashboard itself (restart). */
export async function postGlobal<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(`/api${path}`, postInit(body))
}

/**
 * `data` of the envelope, or an ApiError with its error.code. A `tolerated` error code whose
 * envelope still carries `data` (a report like `checks_failed`) returns that data.
 */
async function readEnvelope<T>(response: Response, tolerated: readonly string[] = []): Promise<T> {
  let body: Envelope<T>
  try {
    body = (await response.json()) as Envelope<T>
  } catch {
    throw new ApiError('bad_response', `HTTP ${response.status}: not a JSON envelope`)
  }
  if (!body.ok && body.data !== null && body.error && tolerated.includes(body.error.code)) {
    return body.data
  }
  if (!body.ok || body.data === null) {
    const error = body.error
    const code = error?.code ?? 'unknown'
    throw new ApiError(
      code,
      code === DB_BUSY_CODE ? DB_BUSY_MESSAGE : (error?.message ?? `HTTP ${response.status}`),
      toIssues(error?.issues),
      body.ok ? null : (body.data ?? null),
    )
  }
  return body.data
}

function str(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function toIssues(raw: unknown): ApiIssue[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((i): i is Record<string, unknown> => typeof i === 'object' && i !== null)
    .map((i) => ({
      code: str(i.code) ?? 'unknown',
      message: str(i.message) ?? '',
      path: str(i.path),
      id: str(i.id),
    }))
}

export interface Health {
  app: string
  version: string
  /** The dashboard's home folder (HAIFA_HOME) with the registry. */
  home: string
}

export function fetchHealth(): Promise<Health> {
  return getGlobal<Health>('/health')
}

export type RepoStatus = 'ok' | 'uncommitted' | 'not_installed' | 'missing' | 'not_git'

/** One registered repository of GET /api/repos. */
export interface RepoItem {
  id: string
  name: string
  path: string
  added_at: string
  status: RepoStatus
  factory: Record<string, unknown> | null
}

export interface RepoList {
  repos: RepoItem[]
  home: string
}

export function fetchRepos(): Promise<RepoList> {
  return getGlobal<RepoList>('/repos')
}

/** The running phase of a run on the overview. */
export interface OverviewPhase {
  name: string
  attempt: number | null
  started_at: string | null
}

/** A run in the `running` state (GET /api/overview). */
export interface OverviewRunning {
  run_id: string
  task_id: string
  task_title: string | null
  workflow: string | null
  started_at: string | null
  phase: OverviewPhase | null
  cost: number
  tokens: number
  /** `ended`: the run's process is gone ("proces skončil"), the row stays as it is. */
  process: 'alive' | 'ended' | 'unknown'
  status_label: string | null
  /** The run's pause: asked for (the phase still runs), in effect, or none. */
  pause?: 'pausing' | 'paused' | null
}

/** An open task PR of the trace without a running run. */
export interface OverviewReview {
  task_id: string
  task_title: string | null
  pr_id: string | null
  url: string | null
  branch: string | null
  opened_at: string | null
  age_s: number | null
  source: string
}

/** A task whose newest PR was merged outside factory and that is not done in base yet. */
export interface OverviewMergedOutside {
  task_id: string
  task_title: string | null
  pr_id: string | null
  url: string | null
  branch: string | null
  merged_at: string | null
}

/** The newest open `factory backlog sync` PR of a repo. */
export interface OverviewSyncPr {
  url: string
  branch: string
  tasks: string[]
}

/** A task whose newest run ended failed or aborted. */
export interface OverviewFailed {
  run_id: string
  task_id: string
  task_title: string | null
  state: string
  workflow: string | null
  ended_at: string | null
  error: string | null
}

export interface OverviewConfig {
  factory_state: string
  installed: boolean
  base: string | null
  commit: string | null
  invalid: boolean
  issues: string[]
  uncommitted: Record<string, unknown>[]
  clean: boolean
}

export type OverviewState =
  | 'ok'
  | 'uncommitted'
  | 'not_installed'
  | 'invalid_config'
  | 'missing'
  | 'not_git'
  | 'timeout'
  | 'error'

/** Tasks of a repo per kanban board state (GET /api/overview `tasks`). */
export type OverviewTaskCounts = Record<BoardState, number>

/** The progress of a stop or pause of the whole repo the dashboard started. */
export interface OverviewControl {
  action: 'stop' | 'pause'
  run_ids: string[]
  /** Stops still on their way (a pause reads its progress from the runs' `pause`). */
  pending: string[]
  errors: { run_id: string; task_id?: string | null; code: string; message: string }[]
  started_at: string
  finished_at: string | null
}

/** What the factory controls of a repo need (GET /api/overview `factory`). */
export interface OverviewFactory {
  max_parallel_runs: number | null
  running: number
  free_slots: number
  /** Ready tasks not excluded from auto-continue. */
  ready: number
  can_start: boolean
  paused: number
  pausing: number
  control: OverviewControl | null
}

/** A task the factory start did not start, and why (run.queue SKIP_REASONS). */
export interface FactorySkip {
  task_id: string
  reason: string
  detail: string
  waits_on: string[]
}

/** POST /api/repos/{id}/control/start. */
export interface FactoryStartResult {
  max_parallel_runs: number
  running: number
  free_slots: number
  started: { task_id: string; run_id: string | null }[]
  skipped: FactorySkip[]
}

/** POST /api/repos/{id}/control/pause|resume. */
export interface FactoryPauseResult {
  action: 'pause' | 'resume'
  run_ids: string[]
  errors: OverviewControl['errors']
}

/** POST /api/repos/{id}/control/stop (the stops go on in the background). */
export interface FactoryStopResult {
  action: 'stop'
  run_ids: string[]
  pending: string[]
}

/** One repository of GET /api/overview. */
export interface OverviewRepo {
  id: string
  name: string
  path: string
  state: OverviewState
  has_trace: boolean
  running: OverviewRunning[]
  review: OverviewReview[]
  failed: OverviewFailed[]
  /** Tasks merged outside factory that `factory backlog sync` would mark done. */
  merged_outside?: OverviewMergedOutside[]
  sync_pr?: OverviewSyncPr | null
  config: OverviewConfig | null
  last_activity: string | null
  warnings: string[]
  /** Null for a repo that is missing, not git, slow or broken. */
  tasks?: OverviewTaskCounts | null
  factory?: OverviewFactory | null
}

export interface OverviewData {
  repos: OverviewRepo[]
  totals: Record<string, number>
}

/** What runs, waits for review and failed in every registered repo; reads only. */
export async function fetchOverview(): Promise<OverviewData> {
  const data = await getGlobal<Partial<OverviewData>>('/overview')
  const repos = Array.isArray(data.repos) ? data.repos : []
  return {
    repos: repos.map((r) => ({
      ...r,
      running: r.running ?? [],
      review: r.review ?? [],
      failed: r.failed ?? [],
      merged_outside: r.merged_outside ?? [],
      sync_pr: r.sync_pr ?? null,
      warnings: r.warnings ?? [],
    })),
    totals: data.totals ?? {},
  }
}

function controlPath(repoId: string, action: string): string {
  return `/repos/${encodeURIComponent(repoId)}/control/${action}`
}

/** Start ready tasks of the repo into its free parallel slots. */
export async function controlStart(repoId: string): Promise<FactoryStartResult> {
  return postGlobal<FactoryStartResult>(controlPath(repoId, 'start'), {})
}

/** Pause every running run of the repo. */
export async function controlPause(repoId: string): Promise<FactoryPauseResult> {
  return postGlobal<FactoryPauseResult>(controlPath(repoId, 'pause'), {})
}

/** Resume every paused run of the repo. */
export async function controlResume(repoId: string): Promise<FactoryPauseResult> {
  return postGlobal<FactoryPauseResult>(controlPath(repoId, 'resume'), {})
}

/** Stop every running run of the repo; the progress shows in the overview. */
export async function controlStop(repoId: string): Promise<FactoryStopResult> {
  return postGlobal<FactoryStopResult>(controlPath(repoId, 'stop'), {})
}

/** POST /api/repos/{id}/backlog/sync (`factory backlog sync`). */
export interface BacklogSyncResult {
  url: string | null
  created: boolean
  updated: boolean
  tasks: { task_id: string }[]
}

/** Open (or extend) the sync PR that marks done the tasks merged outside factory. */
export async function backlogSync(repoId: string): Promise<BacklogSyncResult> {
  return postGlobal<BacklogSyncResult>(`/repos/${encodeURIComponent(repoId)}/backlog/sync`, {})
}

/** DELETE /api<path> of the dashboard itself (remove a repo), with an optional JSON body. */
export async function deleteGlobal<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(`/api${path}`, { ...postInit(body), method: 'DELETE' })
}

// ── adding and removing repositories ─────────────────────────────────────────

export type FactoryState = 'none' | 'uncommitted' | 'unsupported' | 'installed'

/** The factory state of a repo (`factory` of inspect and of a RepoItem). */
export interface RepoFactory {
  repo: string
  base: string | null
  commit: string | null
  state: FactoryState
  action: string | null
}

/** Why a folder cannot be added (`problem` of inspect). */
export interface RepoProblem {
  code: string
  message: string
  main_checkout?: string
  repo?: string
}

/** POST /api/repos/inspect: what adding the folder would do; reads only. */
export interface InspectResult {
  path: string
  root: string | null
  subdir: string | null
  registered: string | null
  addable: boolean
  problem: RepoProblem | null
  branch: string | null
  remote: { name: string; url: string } | null
  trace_db: string | null
  factory: RepoFactory | null
}

export function inspectRepo(path: string): Promise<InspectResult> {
  return postGlobal<InspectResult>('/repos/inspect', { path })
}

/** One file a factory install or removal commits. */
export interface CommitFile {
  path: string
  action: string
}

/** `install` of POST /api/repos: the commit of factory from the library on base. */
export interface RepoInstall {
  committed: boolean
  commit: string | null
  pushed: boolean
  files: CommitFile[]
  /** The pull request of an add with base_changes pr (null: committed on base). */
  pr?: { url: string; branch: string } | null
  /** base_pr_merge auto merged it at once. */
  merged?: boolean
}

export interface AddRepoResult {
  repo: RepoItem
  created: boolean
  install: RepoInstall
}

/** Registers the repo and installs factory from the library in one commit on base (or a PR). */
/** How factory changes base from now on (`.factory/config.yaml`); the install already follows it. */
export interface BaseChanges { base_changes?: 'direct' | 'pr'; base_pr_merge?: 'manual' | 'auto' }

export function addRepo(path: string, changes: BaseChanges = {}): Promise<AddRepoResult> {
  return postGlobal<AddRepoResult>('/repos', { path, ...changes })
}

export interface RemovalBlocker {
  code: string
  message: string
  fix?: string
}

/** GET /api/repos/{id}/removal: what removing the repo commits; writes nothing. */
export interface RepoRemoval {
  repo: string
  base: string
  base_sha: string
  target: string
  digest: string
  files: CommitFile[]
  blockers: RemovalBlocker[]
}

export function fetchRepoRemoval(id: string): Promise<RepoRemoval> {
  return getGlobal<RepoRemoval>(`/repos/${encodeURIComponent(id)}/removal`)
}

export interface RemoveRepoOptions {
  uninstall?: boolean
}

export interface RemoveRepoResult {
  removed: Record<string, unknown>
  uninstall: { committed: boolean; commit: string | null; pushed: boolean } | null
}

/** Removes the repo from the dashboard; `uninstall: true` also commits the deletion of .factory/ on base. */
export function removeRepo(id: string, options?: RemoveRepoOptions): Promise<RemoveRepoResult> {
  return deleteGlobal<RemoveRepoResult>(`/repos/${encodeURIComponent(id)}`, options)
}

/** One subfolder of GET /api/fs/dirs. */
export interface FsEntry {
  name: string
  path: string
  is_git: boolean
  has_factory: boolean
}

export interface FsDirs {
  path: string
  parent: string | null
  entries: FsEntry[]
  truncated: boolean
}

/** The subfolders of an absolute `path` under the home folder; the home folder without one. */
export function fetchDirs(path?: string): Promise<FsDirs> {
  return getGlobal<FsDirs>('/fs/dirs' + (path ? `?path=${encodeURIComponent(path)}` : ''))
}

/** Whether this machine has a system folder dialog. */
export function fetchPickStatus(): Promise<{ available: boolean }> {
  return getGlobal<{ available: boolean }>('/fs/pick')
}

/** Opens the system folder dialog: the chosen `path` or `cancelled`. */
export function pickFolder(): Promise<{ path?: string; cancelled?: boolean }> {
  return postGlobal<{ path?: string; cancelled?: boolean }>('/fs/pick')
}

export interface DashboardSettings {
  port: number
  home: string
  registry: string
  restart_required: boolean
}

export function fetchDashboardSettings(): Promise<DashboardSettings> {
  return getGlobal<DashboardSettings>('/dashboard/settings')
}

export function saveDashboardSettings(port: number): Promise<DashboardSettings> {
  return postGlobal<DashboardSettings>('/dashboard/settings', { port })
}

// ── Factory tab ──────────────────────────────────────────────────────────────

export type CheckScope = 'repo' | 'machine' | 'library'
export type CheckSeverity = 'error' | 'warning' | 'info'

export interface CheckFinding {
  code: string
  scope: CheckScope
  severity: CheckSeverity
  message: string
  fix: string | null
  action: string | null
}

/** GET /api/repos/<id>/factory/check: `factory check` plus the package version. */
export interface FactoryCheck {
  in_repo: boolean
  repo: string | null
  state: FactoryState | null
  action: string | null
  base: string | null
  commit: string | null
  remote: string | null
  ahead: number | null
  behind: number | null
  offline: boolean
  ok: boolean
  counts: { error: number; warning: number; info: number }
  findings: CheckFinding[]
  checked_at: string
  cached: boolean
  version: string
}

/** Error codes of the check whose envelope still carries the report. */
export const CHECK_REPORT_CODES = ['checks_failed'] as const

export async function fetchFactoryCheck({ fresh }: { fresh?: boolean } = {}): Promise<FactoryCheck> {
  const url = apiBase() + '/factory/check' + (fresh ? '?fresh=1' : '')
  return readEnvelope<FactoryCheck>(await fetch(url), CHECK_REPORT_CODES)
}


export type FactoryAction = 'init' | 'config_commit' | 'pull'
export interface FactoryOptions {
  base?: string; provider?: string
  azure?: { organization: string; project: string; repository: string }
  docs_root?: string
}
export interface FactoryFile {
  path: string; action: string; diff: string; content: string | null; binary: boolean; mode?: string | null
}
/** What stops a plan from being applied (factory and library plans alike). */
export interface PlanBlocker { code: string; message: string; fix?: string }
/** A plan warning: plain text or a coded message. */
export type PlanWarning = string | { code?: string; message: string }
/** One library item a plan adds, updates or leaves. */
export interface PlanItem { type: string; name: string; action: string; version?: string }
interface FactoryPlanCommon {
  base: string; base_sha: string; remote?: string | null; digest: string
  files: FactoryFile[]; blockers: PlanBlocker[]
  warnings?: PlanWarning[]; envelopeWarnings?: string[]
}
export interface FactoryInitPlan extends FactoryPlanCommon {
  action: 'init'
  provider: string; azure?: FactoryOptions['azure'] | null; docs_root: string
  detected: { harnesses: Record<string, { installed: boolean }> }
}
export interface FactoryConfigCommitPlan extends FactoryPlanCommon { action: 'config_commit' }
export interface FactoryPullPlan extends FactoryPlanCommon { action: 'pull'; before: string; after: string }
export type FactoryPlan = FactoryInitPlan | FactoryConfigCommitPlan | FactoryPullPlan
export interface FactoryResult { library_commit?: string | null; commit?: string; pr?: { url: string; branch?: string }; after?: string; warnings?: string[] }
export interface FactoryRequest { action: Exclude<FactoryAction, 'pull'>; options: FactoryOptions; target: 'base' | 'pr' }

/** Whitelist plan choices; never serialize the returned files, paths or contents. */
export function factoryChoices(action: FactoryRequest['action'], options: FactoryOptions): FactoryOptions {
  if (action === 'config_commit') return {}
  return { base: options.base, provider: options.provider,
    azure: options.provider === 'azure' && options.azure ? {
      organization: options.azure.organization, project: options.azure.project, repository: options.azure.repository,
    } : undefined,
    docs_root: options.docs_root }
}
function factoryUrl(path: string, id?: string): string {
  return (id ? `/api/repos/${encodeURIComponent(id)}` : apiBase()) + path
}
export function fetchFactoryPlan(body: FactoryRequest, id?: string): Promise<FactoryPlan> {
  return factoryEnvelope<FactoryPlan>(factoryUrl('/factory/plan', id), postInit({
    action: body.action, options: factoryChoices(body.action, body.options), target: body.target,
  }))
}
async function factoryEnvelope<T extends { warnings?: unknown }>(url: string, init?: RequestInit): Promise<T & { envelopeWarnings: string[] }> {
  const response = await fetch(url, init)
  const envelope = await response.clone().json() as Envelope<T>
  const data = await readEnvelope<T>(response)
  return { ...data, envelopeWarnings: envelope.warnings ?? [] }
}
/** A write result with the result's and the envelope's warnings merged, each once. */
async function applyEnvelope(url: string, body: unknown): Promise<FactoryResult & { envelopeWarnings: string[] }> {
  const result = await factoryEnvelope<FactoryResult>(url, postInit(body))
  return { ...result, warnings: [...new Set([...(result.warnings ?? []), ...result.envelopeWarnings])] }
}
export function applyFactoryPlan(body: FactoryRequest & { digest: string; message: string }, id?: string): Promise<FactoryResult> {
  return applyEnvelope(factoryUrl('/factory/apply', id), { action: body.action,
    options: factoryChoices(body.action, body.options), target: body.target, digest: body.digest, message: body.message })
}
export function fetchBasePullPlan(id?: string): Promise<FactoryPullPlan> {
  return factoryEnvelope<FactoryPullPlan>(factoryUrl('/config/pull/plan', id))
}
export function applyBasePull(digest: string, id?: string): Promise<FactoryResult> {
  return applyEnvelope(factoryUrl('/config/pull', id), { digest })
}

export interface MachineCheck {
  ok: boolean; findings: CheckFinding[]; checked_at: string; cached: boolean
  harness_repos?: Record<string, number>
  /** Every missing harness, also those whose info finding is not shown (no repo uses them). */
  missing_harnesses?: string[]
}
export async function fetchMachineCheck(fresh = false): Promise<MachineCheck> {
  return readEnvelope<MachineCheck>(await fetch('/api/machine/check' + (fresh ? '?fresh=1' : '')), CHECK_REPORT_CODES)
}

export type FactoryItemType = 'agent' | 'workflow' | 'skill' | 'extension'
/** `repo`: the repo's own copy in .factory/; `library`: inherited from the system library or the seed. */
export type FactoryItemOrigin = 'repo' | 'library'
export interface FactoryRepoItem { type: FactoryItemType; name: string; origin: FactoryItemOrigin }
export interface FactoryRosterAgent {
  name: string; purpose?: string; harness?: string; coding_agent?: string; model?: string; thinking?: string
  skills?: string[]; extensions?: string[]; writes?: string[]; origin?: FactoryItemOrigin
  /** The bindings .factory/agents.yaml sets for this agent. */
  overridden?: RosterField[]
  /** The values without those overrides (library and roster defaults); null for the repo's own copy. */
  inherited?: RosterBindingValues | null
}
/** A binding of an agent that the roster can override or reset. */
export type RosterField = 'harness' | 'model' | 'thinking'
export interface RosterBindingValues { harness: string; model: string; thinking: string }
/** A roster preset of `factory roster set --preset`: one harness, model and thinking for every agent. */
export interface RosterPreset { harness: string; model: string; thinking: string }
/** A harness/model/thinking override on a workflow step; it wins over the roster. */
export interface WorkflowOverride {
  workflow: string; step: string; agent?: string | null; harness: string | null; model: string | null; thinking: string | null
}
export interface FactoryRoster {
  agents: FactoryRosterAgent[]; workflow_tasks: Record<string, number>
  presets?: Record<string, RosterPreset>; thinking_levels?: string[]; workflow_overrides?: WorkflowOverride[]
}
/** The effective binding of one agent after a roster change. */
export interface RosterBinding { name: string; harness: string; model: string; thinking: string }
export interface RosterChange {
  preset?: string; agent?: string; harness?: string; model?: string; thinking?: string
  /** Bindings of `agent` whose override is removed, so the inherited value applies again. */
  reset?: RosterField[]
  dry_run: boolean
}
export interface RosterChangeResult {
  agents: RosterBinding[]; before: RosterBinding[]; diff: string; changed: boolean; dry_run?: boolean; comments_preserved?: boolean
}
/** The item a move plan writes to the library and deletes from the repo. */
export interface MoveOptions { type: FactoryItemType; name: string }
export interface FactoryMovePlan extends FactoryPlanCommon {
  action: 'move'; type: FactoryItemType; name: string; target: string
  library: string | null
  library_plan: { digest: string; files: FactoryFile[]; blockers?: PlanBlocker[]; warnings?: PlanWarning[] }
}
export function fetchFactoryItems(id: string): Promise<{ library: string | null; library_name?: string | null; items: FactoryRepoItem[] }> {
  return request(factoryUrl('/factory/items', id))
}
export function fetchFactoryRoster(id: string): Promise<FactoryRoster> {
  return request(factoryUrl('/factory/roster', id))
}
/** Changes .factory/agents.yaml in the working tree (`dry_run` only previews); runs use it after a config commit. */
export function saveFactoryRoster(change: RosterChange, id: string): Promise<RosterChangeResult> {
  return request(factoryUrl('/factory/roster', id), postInit(change))
}
/** Plans moving the repo's own copy of an item to the library; writes nothing. */
export function previewMove(options: MoveOptions, id: string): Promise<FactoryMovePlan> {
  return factoryEnvelope<FactoryMovePlan>(factoryUrl('/factory/plan', id),
    postInit({ action: 'move', options: { type: options.type, name: options.name }, target: 'base' }))
}
/** Applies the reviewed move plan: library commit, deletion from the repo and its commit on base. */
export function applyMove(options: MoveOptions, digest: string, id: string): Promise<FactoryResult> {
  return applyEnvelope(factoryUrl('/factory/apply', id),
    { action: 'move', options: { type: options.type, name: options.name }, target: 'base', digest })
}

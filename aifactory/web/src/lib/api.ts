// The dashboard API answers in the same envelope as `factory --json`. Repo endpoints live under
// /api/repos/<id> of the repo in the URL; health, the repo list, code and restart are global.
import { currentRepoId } from './router'
import { onboardingRequest, type OnboardingPlan } from './onboarding'

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
  config: OverviewConfig | null
  last_activity: string | null
  warnings: string[]
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
      warnings: r.warnings ?? [],
    })),
    totals: data.totals ?? {},
  }
}

/** DELETE /api<path> of the dashboard itself (remove a repo); no body. */
export async function deleteGlobal<T>(path: string): Promise<T> {
  return request<T>(`/api${path}`, { method: 'DELETE' })
}

// ── adding and removing repositories ─────────────────────────────────────────

export type FactoryState = 'none' | 'working_tree' | 'sssf' | 'pre_library' | 'onboarded'
export type OnboardingSource = 'init' | 'sssf' | 'pre_library'

/** The `onboarding` block of the manifest in base. */
export interface Onboarding {
  source: OnboardingSource
  source_commit: string | null
  at: string
  by: string | null
  factory: string
  library_commit: string | null
}

/** The factory state of a repo (`factory` of inspect and of a RepoItem). */
export interface RepoFactory {
  onboarding_state?: 'onboarded_in_remote' | 'onboarding_pending' | null
  onboarding_pr?: { id: string; url: string } | null
  repo: string
  base: string | null
  commit: string | null
  state: FactoryState
  action: string | null
  sssf_leftover: boolean
  alternate_rosters: boolean
  rosters?: unknown
  onboarding: Onboarding | null
  library: Record<string, unknown> | null
  manifest_error: string | null
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
  sssf_paths?: string[]
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

export function addRepo(path: string, removeSssf = false): Promise<{ repo: RepoItem; created: boolean }> {
  return postGlobal<{ repo: RepoItem; created: boolean }>('/repos', { path, ...(removeSssf ? { remove_sssf: true } : {}) })
}

/** Removes the repo from the dashboard registry only; nothing in the repo changes. */
export function removeRepo(id: string): Promise<{ removed: Record<string, unknown> }> {
  return deleteGlobal<{ removed: Record<string, unknown> }>(`/repos/${encodeURIComponent(id)}`)
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

/** GET /api/repos/<id>/factory/check: `factory check` plus the manifest and the version. */
export interface FactoryCheck {
  onboarding_state?: 'onboarded_in_remote' | 'onboarding_pending' | null
  onboarding_pr?: { id: string; url: string } | null
  library?: { name: string; remote?: string | null } | null
  in_repo: boolean
  repo: string | null
  state: FactoryState | null
  action: string | null
  sssf_leftover: boolean
  alternate_rosters: boolean
  onboarding: Onboarding | null
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
  manifest: { format: number; written_by: string } | null
  manifest_error: string | null
  version: string
}

/** Error codes of the check whose envelope still carries the report. */
export const CHECK_REPORT_CODES = ['checks_failed'] as const

export async function fetchFactoryCheck({ fresh }: { fresh?: boolean } = {}): Promise<FactoryCheck> {
  const url = apiBase() + '/factory/check' + (fresh ? '?fresh=1' : '')
  return readEnvelope<FactoryCheck>(await fetch(url), CHECK_REPORT_CODES)
}


export type FactoryAction = 'init' | 'update' | 'config_commit' | 'pull'
export interface AgentBinding { harness: string; model: string | null; thinking: string | null }
export interface FactoryOptions {
  base?: string; provider?: string
  azure?: { organization: string; project: string; repository: string }
  backlog_dir?: string; specs_dir?: string; docs_dir?: string
  agents?: string[]; workflows?: string[]; bind?: Record<string, AgentBinding>
  take?: string[]; merge?: string[]; migrate?: string[]
}
export interface FactoryFile {
  path: string; action: string; diff: string; content: string | null; binary: boolean; mode?: string | null
}
export interface UpdateFile { file: string; status: string; diff: string | null; ours_diff: string | null; theirs_diff: string | null }
/** What stops a plan from being applied (factory, library and onboarding plans alike). */
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
  provider: string; azure?: FactoryOptions['azure'] | null; backlog_dir: string; specs_dir: string; docs_dir: string
  agents: string[]; workflows: string[]; added_agents: string[]; bindings: Record<string, AgentBinding>
  detected: { harnesses: Record<string, { installed: boolean }> }
  available: { agents: (AgentBinding & { name: string; purpose: string; default: boolean })[]; workflows: { name: string; default: boolean }[] }
}
export interface FactoryUpdatePlan extends FactoryPlanCommon {
  action: 'update'
  update: { items: { type: string; name: string; action: string; merge_available: boolean; files: UpdateFile[] }[]; migrations: { id: string; title: string; diff: string; selected: boolean; applied: boolean }[] }
}
export interface FactoryConfigCommitPlan extends FactoryPlanCommon { action: 'config_commit' }
export interface FactoryPullPlan extends FactoryPlanCommon { action: 'pull'; before: string; after: string }
export type FactoryPlan = FactoryInitPlan | FactoryUpdatePlan | FactoryConfigCommitPlan | FactoryPullPlan
export interface FactoryResult { library_commit?: string; commit?: string; pr?: { url: string; branch?: string }; after?: string; warnings?: string[] }
export interface FactoryRequest { action: Exclude<FactoryAction, 'pull'>; options: FactoryOptions; target: 'base' | 'pr' }

/** Whitelist plan choices; never serialize the returned files, paths or contents. */
export function factoryChoices(action: FactoryRequest['action'], options: FactoryOptions): FactoryOptions {
  if (action === 'config_commit') return {}
  if (action === 'update') return { take: options.take ?? [], merge: options.merge ?? [], migrate: options.migrate ?? [] }
  const bind: Record<string, AgentBinding> = {}
  for (const name of options.agents ?? []) {
    const entry = options.bind?.[name]
    if (entry) bind[name] = { harness: entry.harness, model: entry.model, thinking: entry.thinking }
  }
  return { base: options.base, provider: options.provider,
    azure: options.provider === 'azure' && options.azure ? {
      organization: options.azure.organization, project: options.azure.project, repository: options.azure.repository,
    } : undefined,
    backlog_dir: options.backlog_dir, specs_dir: options.specs_dir, docs_dir: options.docs_dir,
    agents: options.agents, workflows: options.workflows, bind }
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
export function previewOnboarding(id: string, action: 'onboard' | 'adopt', target: 'base' | 'pr') {
  return factoryEnvelope<OnboardingPlan>(factoryUrl('/factory/plan', id), postInit(onboardingRequest(action, target)))
}
export function applyOnboarding(id: string, action: 'onboard' | 'adopt', target: 'base' | 'pr', digest: string, message: string) {
  return applyEnvelope(factoryUrl('/factory/apply', id), onboardingRequest(action, target, digest, message))
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
}
export async function fetchMachineCheck(fresh = false): Promise<MachineCheck> {
  return readEnvelope<MachineCheck>(await fetch('/api/machine/check' + (fresh ? '?fresh=1' : '')), CHECK_REPORT_CODES)
}

export type FactoryItemType = 'agent' | 'workflow' | 'skill' | 'extension'
export type FactoryItemState = 'local' | 'missing' | 'synced' | 'unknown' | 'outdated' | 'modified' | 'diverged'
export interface FactoryRepoItem {
  type: FactoryItemType; name: string; item: string | null; state: FactoryItemState
  repo_version: string | null; manifest_version: string | null; library_version: string | null
}
export interface FactoryRosterAgent {
  name: string; purpose?: string; harness?: string; coding_agent?: string; model?: string; thinking?: string
  skills?: string[]; extensions?: string[]; writes?: string[]
}
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
  preset?: string; agent?: string; harness?: string; model?: string; thinking?: string; dry_run: boolean
}
export interface RosterChangeResult {
  agents: RosterBinding[]; before: RosterBinding[]; diff: string; changed: boolean; dry_run?: boolean; comments_preserved?: boolean
}
export interface FactoryItemDiffSide {
  available: boolean; reason?: string; version?: string
  files: { path: string; status: string; binary: boolean; diff: string | null }[]
}
export interface FactoryItemDiff { manifest: FactoryItemDiffSide; head: FactoryItemDiffSide }
export type FactoryItemAction = 'add' | 'update' | 'export' | 'revert' | 'remove'
export interface FactoryItemOptions {
  type?: FactoryItemType; name?: string; slot?: string; agent?: string
  harness?: string; model?: string; thinking?: string; to?: 'manifest' | 'head'; prune?: boolean
  item?: string[]; take?: string[]; merge?: string[]; migrate?: string[]
}
export interface FactoryItemRequest { action: FactoryItemAction; options: FactoryItemOptions; target: 'base' | 'pr' }
export interface FactoryItemPlan extends FactoryPlanCommon {
  items?: PlanItem[]
  update?: FactoryUpdatePlan['update']
  library_plan?: { digest: string; items: PlanItem[]; files: FactoryFile[]; blockers: PlanBlocker[] }
  added?: { type: string; name: string; action?: string }[]
  kept?: { type: string; name: string; reason?: string }[]
}
export function fetchFactoryItems(id: string): Promise<{ items: FactoryRepoItem[] }> {
  return request(factoryUrl('/factory/items', id))
}
export function fetchFactoryRoster(id: string): Promise<FactoryRoster> {
  return request(factoryUrl('/factory/roster', id))
}
/** Changes .factory/agents.yaml in the working tree (`dry_run` only previews); runs use it after a config commit. */
export function saveFactoryRoster(change: RosterChange, id: string): Promise<RosterChangeResult> {
  return request(factoryUrl('/factory/roster', id), postInit(change))
}
export function fetchFactoryItemDiff(item: FactoryRepoItem, id: string): Promise<FactoryItemDiff> {
  return request(factoryUrl(`/factory/item-diff?type=${item.type}&name=${encodeURIComponent(item.name)}`, id))
}
export function factoryItemChoices(action: FactoryItemAction, options: FactoryItemOptions): FactoryItemOptions {
  const keys = {
    add: ['type', 'name', 'slot', 'agent', 'harness', 'model', 'thinking'],
    update: ['item', 'take', 'merge', 'migrate'], export: ['type', 'name', 'slot'],
    revert: ['type', 'name', 'to'], remove: ['type', 'name', 'prune'],
  }[action]
  return Object.fromEntries(Object.entries(options).filter(([key]) => keys.includes(key)))
}
export function previewFactoryItem(body: FactoryItemRequest, id: string): Promise<FactoryItemPlan> {
  return factoryEnvelope<FactoryItemPlan>(factoryUrl('/factory/plan', id), postInit({ action: body.action, options: factoryItemChoices(body.action, body.options), target: body.target }))
}
export function applyFactoryItem(body: FactoryItemRequest, digest: string, message: string, id: string): Promise<FactoryResult> {
  return factoryEnvelope<FactoryResult>(factoryUrl('/factory/apply', id), postInit({ action: body.action, options: factoryItemChoices(body.action, body.options), target: body.target, digest, message }))
}

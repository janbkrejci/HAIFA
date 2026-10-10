// The backlog tree, kanban and task writes, as served by /api/backlog (aifactory/web/backlog.py).
// Writes call the same core functions as `factory task add|edit|link`.
import { ref } from 'vue'
import { ApiError, getApi, postApi, type ApiIssue } from './api'
import { toCommitStatus, type CommitStatus } from './commitStatus'
import { errorText } from './format'

export type BoardState =
  | 'todo'
  | 'ready'
  | 'blocked'
  | 'running'
  | 'in review'
  | 'done'
  | 'cancelled'

/** Kanban columns, in order. */
export const BOARD_STATES: readonly BoardState[] = [
  'todo',
  'ready',
  'blocked',
  'running',
  'in review',
  'done',
  'cancelled',
]

export const STATE_LABELS: Record<BoardState, string> = {
  todo: 'Bez workflow',
  ready: 'Připraveno',
  blocked: 'Blokováno',
  running: 'Běží',
  'in review': 'V review',
  done: 'Hotovo',
  cancelled: 'Zrušeno',
}

/** Tooltips of the board states that need an explanation. */
export const STATE_TOOLTIPS: Partial<Record<BoardState, string>> = {
  todo: 'Task nejde spustit, dokud nemá workflow (vlastní nebo zděděné z projektu či stepu).',
}

/** A kanban column: a board state, or Odloženo (tasks excluded from auto continue). */
export type KanbanColumn = BoardState | 'deferred'

/** Column labels of the kanban: the board states and Odloženo. */
export const COLUMN_LABELS: Record<KanbanColumn, string> = { ...STATE_LABELS, deferred: 'Odloženo' }

/** Board states whose excluded tasks move to Odloženo (they have not started yet). */
export const DEFERRABLE_STATES: readonly BoardState[] = ['ready', 'blocked', 'todo']

/** The kanban column of a task: Odloženo for an excluded task that has not started. */
export function kanbanColumn(task: Pick<TaskNode, 'board_state' | 'auto_excluded'>): KanbanColumn {
  return task.auto_excluded && DEFERRABLE_STATES.includes(task.board_state) ? 'deferred' : task.board_state
}

/** Kanban columns for `states`: Odloženo always right after Připraveno (a drop target). */
export function kanbanColumns(states: readonly BoardState[]): KanbanColumn[] {
  const out: KanbanColumn[] = []
  for (const s of states) {
    out.push(s)
    if (s === 'ready') out.push('deferred')
  }
  if (!out.includes('deferred')) out.push('deferred')
  return out
}

/**
 * The whole queue after reordering `shown` (the ready tasks the kanban shows, maybe filtered):
 * the ready tasks of `all` keep their places, the shown ones take theirs in the new order.
 */
export function mergeQueueOrder(all: readonly string[], shown: readonly string[]): string[] {
  const moved = new Set(shown)
  const out = [...all]
  const slots = out.map((id, i) => (moved.has(id) ? i : -1)).filter((i) => i >= 0)
  const next = shown.filter((id) => all.includes(id))
  slots.forEach((slot, n) => {
    out[slot] = next[n] ?? out[slot]
  })
  return out
}

/** States shown only when some task is in them (kanban column, status filter option). */
export const OPTIONAL_STATES: readonly BoardState[] = ['todo']

/** States hidden by the „Skrýt hotové“ switch. */
export const DONE_STATES: readonly BoardState[] = ['done', 'cancelled']

/** Default `levels` of `.factory/config.yaml`. */
export const DEFAULT_LEVELS: readonly string[] = ['project', 'step', 'task']

/** Czech names of the known levels: [label, lowercase nominative, lowercase genitive]. */
const LEVEL_NAMES: Record<string, readonly [string, string, string]> = {
  project: ['Projekt', 'projekt', 'projektu'],
  module: ['Modul', 'modul', 'modulu'],
  step: ['Step', 'step', 'stepu'],
  task: ['Task', 'task', 'tasku'],
}

/** The label of a level (`project` → Projekt, `module` → Modul); another name unchanged. */
export function levelLabel(level: string): string {
  return LEVEL_NAMES[level]?.[0] ?? level
}

/** The level in a sentence: lowercase nominative (`projekt`) or genitive (`projektu`). */
export function levelNoun(level: string, form: 'nom' | 'gen' = 'nom'): string {
  const names = LEVEL_NAMES[level]
  if (!names) return level
  return form === 'gen' ? names[2] : names[1]
}

/** Levels joined for a sentence: `projektu nebo stepu`. */
export function levelsText(levels: readonly string[], form: 'nom' | 'gen' = 'nom'): string {
  return levels.map((l) => levelNoun(l, form)).join(' nebo ')
}

/** `levels` of an answer, or the default ones. */
export function levelsOf(levels: unknown): string[] {
  return Array.isArray(levels) && levels.length && levels.every((l) => typeof l === 'string')
    ? [...levels]
    : [...DEFAULT_LEVELS]
}

/** Title and level of a project, step or task id (GET /api/backlog/names). */
export interface CodeName {
  title: string | null
  level: string
}

export type CodeNames = Record<string, CodeName>

export interface BacklogNames {
  levels: string[]
  names: CodeNames
}

/** Tooltip of a code: `Task: <název>`; '' when the code is not known. */
export function codeTooltip(id: string | null | undefined, names: CodeNames): string {
  if (!id) return ''
  const name = Object.prototype.hasOwnProperty.call(names, id) ? names[id] : undefined
  if (!name) return ''
  const label = levelLabel(name.level)
  return name.title ? `${label}: ${name.title}` : label
}

/** A code with its title for text: `<kód> (<název>)`, the code alone when unknown. */
export function codeWithTitle(id: string, names: CodeNames): string {
  const title = names[id]?.title
  return title ? `${id} (${title})` : id
}

/** Names of every container and task in a backlog tree (and the kanban task list). */
export function namesFromBacklog(items: readonly BacklogNode[] | undefined, tasks?: readonly TaskNode[]): CodeNames {
  const out: CodeNames = {}
  const walk = (nodes: readonly BacklogNode[]) => {
    for (const node of nodes) {
      if (node.kind === 'task') {
        if (node.id) out[node.id] = { title: node.title ?? null, level: node.level }
      } else {
        if (node.id) out[node.id] = { title: node.title ?? null, level: node.level }
        if (Array.isArray(node.children)) walk(node.children)
      }
    }
  }
  if (Array.isArray(items)) walk(items)
  if (Array.isArray(tasks)) for (const t of tasks) if (t.id) out[t.id] = { title: t.title ?? null, level: t.level }
  return out
}

export function fetchNames(): Promise<BacklogNames> {
  return getApi<BacklogNames>('/backlog/names')
}

export interface Unmet {
  id: string
  reason: string
  missing: string[]
}

/**
 * Czech noun for a container dependency: its level from `names`, otherwise by the id
 * (one-segment ids such as M01 or HAIFA are projects, longer ones steps).
 */
export function containerNoun(id: string, names: CodeNames = {}): string {
  const level = names[id]?.level
  if (level) return levelNoun(level)
  return id.split('-').length > 1 ? 'step' : 'projekt'
}

/** One line of the Blokováno tooltip: `<kód> (<název>) – <důvod>`. */
export function unmetLine(u: Unmet, names: CodeNames = {}): string {
  const code = codeWithTitle(u.id, names)
  const task = levelNoun(names[u.id]?.level ?? 'task')
  switch (u.reason) {
    case 'not_done':
      return `${code} – ${task} není hotový`
    case 'cancelled':
      return `${code} – ${task} je zrušený`
    case 'unknown':
      return `${code} – položka neexistuje`
    case 'empty':
      return `${code} – ${containerNoun(u.id, names)} je prázdný`
    case 'incomplete':
      return `${code} – ${containerNoun(u.id, names)} má nehotové tasky: ${u.missing
        .map((m) => codeWithTitle(m, names))
        .join(', ')}`
    default:
      return `${code} – ${u.reason}`
  }
}

/** Tooltip text of the Blokováno badge; '' when nothing blocks. */
export function blockedTooltip(blockedBy: readonly Unmet[] | undefined, names: CodeNames = {}): string {
  if (!blockedBy?.length) return ''
  return ['Blokuje:', ...blockedBy.map((u) => unmetLine(u, names))].join('\n')
}

export interface TaskNode {
  kind: 'task'
  id: string
  title: string
  level: string
  path: string
  status: string
  state: string
  workflow: string | null
  effective: Record<string, unknown>
  depends_on: string[]
  related: string[]
  writes: string[]
  own_writes: string[]
  blocked_by: Unmet[]
  blocks: string[]
  board_state: BoardState
  /** The task's own `workflow` (null when inherited or missing). */
  own_workflow: string | null
  /** The task's own `auto_merge` (null: inherited). */
  own_parameters?: Record<string, unknown>
  own_auto_merge?: boolean | null
  /** `auto_merge` inherited from task, step or project. */
  effective_auto_merge?: boolean
  invalid: boolean
  last_run: string | null
  /** Place in the kanban's manual queue (0 first); null without a manual place. */
  queue_rank?: number | null
  /** Excluded from auto continue (kanban column Odloženo); a manual run still works. */
  auto_excluded?: boolean
}

export interface ContainerNode {
  kind: 'container'
  id: string | null
  title: string | null
  level: string
  path: string
  progress: { done: number; total: number }
  /** Number of descendant tasks per board state (all of them, no filter applies). */
  state_counts?: Partial<Record<BoardState, number>>
  done: boolean
  blocks: string[]
  children: BacklogNode[]
  /** The container's own `auto_continue` (null: inherited). */
  auto_continue?: boolean | null
  /** The container's own `auto_merge` (null: inherited). */
  auto_merge?: boolean | null
  /** `auto_continue` and `auto_merge` inherited from the container or above. */
  effective_auto_continue?: boolean
  effective_auto_merge?: boolean
  /** The container has an index.md: its switches can be written. */
  can_toggle?: boolean
}

export type BacklogNode = TaskNode | ContainerNode

export interface StepRef {
  harness?: string
  id: string
  title: string | null
  path: string
  /** The project (top level) of the step. */
  project: string | null
}

/** The list shows the tree or the kanban board. */
export type BacklogMode = 'tree' | 'kanban'

export interface BacklogFilters {
  /** Kanban only: tasks of this project (top level); undefined means all. */
  project?: string
  /** Kanban only: tasks of this step; undefined means all. */
  step?: string
}

export interface BacklogData {
  levels: string[]
  backlog_dir: string
  filters: { status: BoardState | null }
  states: BoardState[]
  workflows: string[]
  steps: StepRef[]
  items: BacklogNode[]
  tasks: TaskNode[]
  issues: ApiIssue[]
  counts: Record<string, number>
  /** Number of tasks per board state over the whole backlog (the status filter ignored). */
  state_counts?: Partial<Record<BoardState, number>>
}

export interface DependsRef {
  id: string
  kind: 'task' | 'container' | 'unknown'
  title: string | null
  state: string
}

export interface BlocksRef {
  id: string
  title: string
  board_state: BoardState
}

export interface TaskRun {
  run_id: string
  task_id: string
  branch: string
  worktree: string
  base: string
  base_sha: string
  head_sha: string | null
  state: string
  started_at: string
  ended_at: string | null
  pid: number | null
  workflow: string | null
  note: string | null
  error: string | null
  /** A running run's pause: 'pausing' or 'paused' (factory task pause). */
  pause?: string | null
}

export interface TaskPr {
  branch: string
  task_id: string
  provider: string
  pr_id: string
  url: string
  base: string
  base_sha: string
  title: string
  body: string
  state: string
  created_at: string
  updated_at: string
  merged_at: string | null
  merge_sha: string | null
}

export interface TaskDetail {
  task: TaskNode
  body: string
  issues: ApiIssue[]
  runs: TaskRun[]
  prs: TaskPr[]
  depends: DependsRef[]
  blocks: BlocksRef[]
}

export interface WriteResult {
  requires_config_commit?: boolean
  created_workflow?: string
  action: 'add' | 'edit' | 'link'
  changed: boolean
  path: string
  task: TaskNode
  issues: ApiIssue[]
}

export interface AddTaskInput {
  parameters?: Record<string, unknown>
  workflow_advice_id?: string
  step: string
  title: string
  id?: string
  slug?: string
  workflow?: string
  writes?: string[]
  depends_on?: string[]
  related?: string[]
  body?: string
}

export interface EditTaskInput {
  parameters?: Record<string, unknown>
  body?: string
  depends_on?: string[]
  related?: string[]
  workflow_advice_id?: string
  title?: string
  status?: 'todo' | 'cancelled'
  workflow?: string
  clear_workflow?: boolean
  writes?: string[]
  clear_writes?: boolean
  auto_merge?: boolean
  clear_auto_merge?: boolean
}

export interface LinkInput {
  depends_on?: string[]
  related?: string[]
  remove?: boolean
}

/** A failed write, shown under the form: the message and the validation issues. */
export interface WriteError {
  message: string
  issues: ApiIssue[]
  /** error.code of the API (e.g. `unmet_dependencies`). */
  code?: string
}

/** `factory config status` (D4): shared config not committed to base. */
export type ConfigStatus = CommitStatus

/** What to know before `factory task run`. */
export interface RunCheck {
  task_id: string
  base: string
  config: ConfigStatus | null
  in_base: boolean
  unmet: Unmet[]
  running: TaskRun | null
  launcher_busy: boolean
  /** Effective workflow and writes of the task in base (newer servers). */
  workflow?: string | null
  writes?: string[] | null
}

export interface RunStart {
  task_id: string
  run: TaskRun | null
  /** The run was not claimed in time; it is still starting. */
  pending: boolean
  force: boolean
  /** The run continues with further tasks after success (`--auto`). */
  auto?: boolean
}

/** Which run dialog button is running (it shows the spinner). */
export type RunAction = 'start' | 'force' | 'commit'

/** State of the run panel in the task detail, owned by the Backlog view. */
export interface RunPanel {
  open: boolean
  check: RunCheck | null
  loading: boolean
  busy: boolean
  error: WriteError | null
  result: RunStart | null
  /** The dialog button whose action is running (spinner). */
  action: RunAction | null
  /** Start answered `pending`: waiting for the run to show up in live updates. */
  waiting: boolean
}

export interface RunInput {
  note?: string
  force?: boolean
  /** Harness, model and thinking for this run only; absent means the roster. */
  harness?: string
  model?: string
  thinking?: string
  /** Continue with further tasks after success (auto continue, `--auto`). */
  auto?: boolean
}

/** Harnesses a run can use (`aifactory.harness.HARNESSES`). */
export const RUN_HARNESSES: readonly string[] = ['claude', 'codex', 'pi']

/** Thinking levels (`aifactory.harness.override.THINKING_LEVELS`). */
export const THINKING_LEVELS: readonly string[] = ['off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra']

export interface GraphNode {
  id: string
  title: string | null
  kind: 'task' | 'container' | 'unknown'
  board_state: BoardState | null
  /** State text of a container or unknown node ("done", "2/5", "unknown"). */
  state?: string
  step?: string | null
  /** A dependency outside the module or step. */
  external: boolean
}

export interface GraphEdge {
  from: string
  to: string
}

export interface GraphContainer {
  id: string
  title: string | null
  level: string
  path: string
  auto_continue: boolean | null
  effective_auto_continue: boolean
  auto_merge?: boolean | null
  effective_auto_merge?: boolean
  can_toggle: boolean
}

export interface ContainerGraph {
  container: GraphContainer
  nodes: GraphNode[]
  edges: GraphEdge[]
}

/** `factory backlog auto-continue ID --on|--off|--inherit`. */
export type AutoMode = 'on' | 'off' | 'inherit'

export interface AutoContinueResult {
  changed: boolean
  id: string
  level: string
  path: string
  auto_continue: boolean | null
  effective_auto_continue: boolean
  issues: ApiIssue[]
}

export function fetchBacklog(): Promise<BacklogData> {
  return getApi<BacklogData>('/backlog')
}

function taskPath(taskId: string): string {
  return `/backlog/tasks/${encodeURIComponent(taskId)}`
}

export function fetchTask(taskId: string): Promise<TaskDetail> {
  return getApi<TaskDetail>(taskPath(taskId))
}

export function addTask(input: AddTaskInput): Promise<WriteResult> {
  return postApi<WriteResult>('/backlog/tasks', input)
}

export function editTask(taskId: string, input: EditTaskInput): Promise<WriteResult> {
  return postApi<WriteResult>(`${taskPath(taskId)}/edit`, input)
}

export function linkTask(taskId: string, input: LinkInput): Promise<WriteResult> {
  return postApi<WriteResult>(`${taskPath(taskId)}/link`, input)
}

export function fetchRunCheck(taskId: string): Promise<RunCheck> {
  return getApi<RunCheck>(`${taskPath(taskId)}/run-check`)
}

/** `factory backlog commit`: what was committed to base. */
/** Backlog files not committed to base (GET /api/backlog/status); runs read base (D4). */
export type BacklogStatus = CommitStatus

export async function fetchBacklogStatus(): Promise<BacklogStatus | null> {
  return toCommitStatus(await getApi<unknown>('/backlog/status'))
}

export interface BacklogCommitResult {
  committed: boolean
  commit: string | null
  base: string
  paths: string[]
  pushed: boolean
}

/** `factory backlog commit`: commit the backlog changes (only `backlog_dir`) to base. */
export function commitBacklog(message?: string): Promise<BacklogCommitResult> {
  return postApi<BacklogCommitResult>('/backlog/commit', message ? { message } : {})
}

/** `factory task run`: starts on a background thread of the server. */
export function startRun(taskId: string, input: RunInput = {}): Promise<RunStart> {
  return postApi<RunStart>(`${taskPath(taskId)}/run`, input)
}

/** The kanban's order of ready tasks; auto continue takes them in this order. */
export function setQueueOrder(order: string[]): Promise<{ order: string[] }> {
  return postApi<{ order: string[] }>('/backlog/queue/order', { order })
}

/** Exclude a task from auto continue (Odloženo) or return it to the queue. */
export function setAutoExcluded(taskId: string, excluded: boolean): Promise<{ task_id: string; excluded: boolean }> {
  return postApi<{ task_id: string; excluded: boolean }>(`${taskPath(taskId)}/auto-exclude`, { excluded })
}

function containerPath(containerId: string): string {
  return `/backlog/containers/${encodeURIComponent(containerId)}`
}

export function fetchGraph(containerId: string): Promise<ContainerGraph> {
  return getApi<ContainerGraph>(`${containerPath(containerId)}/graph`)
}

export function setAutoContinue(containerId: string, mode: AutoMode): Promise<AutoContinueResult> {
  return postApi<AutoContinueResult>(`${containerPath(containerId)}/auto-continue`, { mode })
}

/** `factory backlog auto-merge ID --on|--off|--inherit`. */
export interface AutoMergeResult {
  changed: boolean
  id: string
  level: string
  path: string
  auto_merge: boolean | null
  effective_auto_merge: boolean
  issues: ApiIssue[]
}

export function setAutoMerge(containerId: string, mode: AutoMode): Promise<AutoMergeResult> {
  return postApi<AutoMergeResult>(`${containerPath(containerId)}/auto-merge`, { mode })
}

/** The switch position of a container's own `auto_continue` / `auto_merge`. */
export function autoMode(value: boolean | null | undefined): AutoMode {
  if (value === true) return 'on'
  if (value === false) return 'off'
  return 'inherit'
}

/** The message and issues of a failed call, for IssueList. */
export function flattenIssues(e: unknown): WriteError {
  if (e instanceof ApiError) return { message: e.message, issues: e.issues, code: e.code }
  return { message: errorText(e), issues: [] }
}

/** Ids typed by the user, separated by commas or whitespace. */
export function splitIds(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/** One path per line; empty lines dropped. */
export function splitLines(text: string): string[] {
  return text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
}

/** Key of a link write, so only the clicked button shows the spinner. */
export function linkActionKey(input: LinkInput): string {
  const kind = input.related?.length ? 'related' : 'depends_on'
  if (input.remove) return `unlink:${kind}:${(input[kind] ?? [])[0] ?? ''}`
  return `link:${kind}`
}

/** The first run not in `known` (a run that started after the click); a running one wins. */
export function newRun<T extends { run_id: string; state?: string }>(
  runs: T[] | null | undefined,
  known: Set<string>,
): T | null {
  const fresh = (Array.isArray(runs) ? runs : []).filter((r) => !known.has(r.run_id))
  return fresh.find((r) => r.state === 'running') ?? fresh[0] ?? null
}

// ── Tree folding ────────────────────────────────────────────────────────────
// The tree starts folded with the projects visible. The browser remembers what the user
// unfolded (localStorage).

/** localStorage key of the unfolded tree nodes (a JSON list of node keys). */
export const TREE_EXPANDED_KEY = 'haifa.backlog.expanded'

/** Key of a container in the folding state: its id, else its path. */
export function nodeKey(node: Pick<ContainerNode, 'id' | 'path'>): string {
  return node.id ?? node.path
}

function loadExpanded(): Set<string> {
  try {
    if (typeof localStorage === 'undefined') return new Set()
    const raw = JSON.parse(localStorage.getItem(TREE_EXPANDED_KEY) ?? '[]') as unknown
    return new Set(Array.isArray(raw) ? raw.filter((k): k is string => typeof k === 'string') : [])
  } catch {
    return new Set()
  }
}

function saveExpanded(keys: Set<string>): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(TREE_EXPANDED_KEY, JSON.stringify([...keys]))
  } catch {
    // storage unavailable: the folding lasts for this visit only
  }
}

const expanded = ref<Set<string> | null>(null)

function expandedKeys(): Set<string> {
  if (!expanded.value) expanded.value = loadExpanded()
  return expanded.value
}

/** Is the container unfolded? */
export function isExpanded(key: string): boolean {
  return expandedKeys().has(key)
}

/** Fold or unfold a container; the browser remembers the choice. */
export function toggleExpanded(key: string): void {
  const next = new Set(expandedKeys())
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
  saveExpanded(next)
}

/** Test helper: forget the folding state and read localStorage again on next use. */
export function resetTreeForTests(): void {
  expanded.value = null
  resetHideDoneForTests()
}

// ── Kanban filter by project and step ────────────────────────────────────────

/** A project or step offered by the kanban filter. */
export interface ScopeOption {
  id: string
  title: string | null
}

/** Ids of the containers above every task of the tree, by task path. */
export function taskAncestors(items: readonly BacklogNode[] | undefined): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>()
  const walk = (nodes: readonly BacklogNode[], above: string[]) => {
    for (const node of nodes) {
      if (node.kind === 'task') out.set(node.path, new Set(above))
      else if (Array.isArray(node.children)) walk(node.children, node.id ? [...above, node.id] : above)
    }
  }
  if (Array.isArray(items)) walk(items, [])
  return out
}

/** Tasks of the kanban in the project and step of the filters, an empty filter meaning all. */
export function filterKanban(
  tasks: readonly TaskNode[],
  items: readonly BacklogNode[] | undefined,
  filters: BacklogFilters,
): TaskNode[] {
  const scopes = [filters.project, filters.step].filter((s): s is string => !!s)
  const above = scopes.length ? taskAncestors(items) : null
  return tasks.filter((t) => {
    if (!above) return true
    const ids = above.get(t.path)
    return !!ids && scopes.every((s) => ids.has(s))
  })
}

/**
 * Projects for the kanban filter: the top of the tree and the projects of the steps
 * (with fewer than three levels the steps are the projects). Titles fall back to `names`.
 */
export function projectOptions(
  items: readonly BacklogNode[] | undefined,
  steps: readonly StepRef[] | undefined,
  names: CodeNames = {},
): ScopeOption[] {
  const out = new Map<string, string | null>()
  const add = (id: string | null | undefined, title: string | null | undefined) => {
    if (!id) return
    const known = out.get(id)
    if (known === undefined || (known === null && title)) out.set(id, title ?? names[id]?.title ?? null)
  }
  for (const node of Array.isArray(items) ? items : []) if (node.kind === 'container') add(node.id, node.title)
  for (const s of Array.isArray(steps) ? steps : []) {
    if (s.project) add(s.project, null)
    else add(s.id, s.title)
  }
  return [...out].map(([id, title]) => ({ id, title })).sort((a, b) => a.id.localeCompare(b.id))
}

/** Steps for the kanban filter: those of `project`, all without a project. */
export function stepOptions(steps: readonly StepRef[] | undefined, project?: string): ScopeOption[] {
  return (Array.isArray(steps) ? steps : [])
    .filter((s) => s.project && (!project || s.project === project))
    .map((s) => ({ id: s.id, title: s.title }))
}

// ── Hide done tasks ─────────────────────────────────────────────────────────
// The „Skrýt hotové“ switch hides Hotovo and Zrušeno tasks from the tree, the kanban and
// the graph. Off by default; the browser remembers the choice (localStorage).

/** localStorage key of the „Skrýt hotové“ switch ('1' on, '0' off). */
export const HIDE_DONE_KEY = 'haifa.backlog.hideDone'

function loadHideDone(): boolean {
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem(HIDE_DONE_KEY) === '1'
  } catch {
    return false
  }
}

const hideDoneState = ref<boolean | null>(null)

/** Is the „Skrýt hotové“ switch on? */
export function hideDone(): boolean {
  if (hideDoneState.value === null) hideDoneState.value = loadHideDone()
  return hideDoneState.value
}

/** Turn the „Skrýt hotové“ switch on or off; the browser remembers it. */
export function setHideDone(on: boolean): void {
  hideDoneState.value = on
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(HIDE_DONE_KEY, on ? '1' : '0')
  } catch {
    // storage unavailable: the choice lasts for this visit only
  }
}

/** Test helper: read the switch from localStorage again on next use. */
export function resetHideDoneForTests(): void {
  hideDoneState.value = null
}

/** Is the task hidden by the „Skrýt hotové“ switch? */
export function isDoneState(state: BoardState | null | undefined): boolean {
  return !!state && DONE_STATES.includes(state)
}

/**
 * The tree without Hotovo and Zrušeno tasks; a container left without a visible task
 * (project, step) is dropped as well.
 */
export function pruneDone(items: readonly BacklogNode[]): BacklogNode[] {
  const out: BacklogNode[] = []
  for (const node of items) {
    if (node.kind === 'task') {
      if (!isDoneState(node.board_state)) out.push(node)
      continue
    }
    const children = pruneDone(Array.isArray(node.children) ? node.children : [])
    if (children.length) out.push({ ...node, children })
  }
  return out
}

/** The graph without Hotovo and Zrušeno tasks and their arrows. */
export function graphWithoutDone(graph: ContainerGraph): ContainerGraph {
  const nodes = (Array.isArray(graph.nodes) ? graph.nodes : []).filter(
    (n) => !(n.kind === 'task' && isDoneState(n.board_state)),
  )
  const ids = new Set(nodes.map((n) => n.id))
  const edges = (Array.isArray(graph.edges) ? graph.edges : []).filter((e) => ids.has(e.from) && ids.has(e.to))
  return { ...graph, nodes, edges }
}

/** Number of tasks per board state: `state_counts` of the answer, else counted from `tasks`. */
export function stateCounts(data: BacklogData | null | undefined): Partial<Record<BoardState, number>> {
  if (data?.state_counts && typeof data.state_counts === 'object') return data.state_counts
  const out: Partial<Record<BoardState, number>> = {}
  for (const t of Array.isArray(data?.tasks) ? data.tasks : []) out[t.board_state] = (out[t.board_state] ?? 0) + 1
  return out
}

/** States worth showing: an optional state (Bez workflow) only when some task is in it. */
export function presentStates(
  states: readonly BoardState[],
  counts: Partial<Record<BoardState, number>>,
): BoardState[] {
  return states.filter((s) => !OPTIONAL_STATES.includes(s) || (counts[s] ?? 0) > 0)
}

// ── Projects and steps: detail, add, edit (index.md) ─────────────────────────
// GET /api/backlog/containers/{id}, POST /api/backlog/containers and
// POST /api/backlog/containers/{id}/edit call the core functions of `factory backlog add|edit`.

/** Keys of a project's or step's `index.md` the settings panel sets or removes. */
export const CONTAINER_KEYS = [
  'harness',
  'model',
  'thinking',
  'workflow',
  'writes',
  'source',
  'target',
  'specs_dir',
  'docs_dir',
  'workdir',
  'auto_continue',
] as const

export type ContainerKey = (typeof CONTAINER_KEYS)[number]

/** Where an effective value comes from: a level, `.factory/config.yaml` or the default. */
export type SettingOrigin =
  | { source: 'own' | 'inherited'; level: string; id: string | null; path: string | null }
  | { source: 'config'; path: string; key: string }
  | { source: 'default' }

export interface EffectiveSetting {
  value: unknown
  origin: SettingOrigin | null
}

export interface ContainerDetail {
  kind: 'container'
  id: string
  title: string | null
  level: string
  path: string
  index_path: string | null
  parent: string | null
  children: string[]
  /** The description of `index.md`. */
  body: string
  /** Inherited keys set in its own `index.md`. */
  own: Record<string, unknown>
  /** Other keys of `index.md`. */
  extra: Record<string, unknown>
  effective: Record<string, EffectiveSetting>
}

export interface ContainerDetailData {
  container: ContainerDetail
  editable_keys: string[]
  issues: ApiIssue[]
}

export interface ContainerWriteResult {
  action: 'add' | 'edit'
  changed: boolean
  path: string
  container: ContainerDetail
  issues: ApiIssue[]
}

export interface AddContainerInput {
  /** The project of a new step; none for a new project. */
  parent?: string
  id: string
  title: string
  body?: string
}

export interface EditContainerInput {
  harness?: string | null
  model?: string | null
  thinking?: string | null
  title?: string
  workflow?: string
  writes?: string[]
  source?: string
  target?: string
  specs_dir?: string | null
  docs_dir?: string | null
  workdir?: string | null
  auto_continue?: boolean
  /** Keys removed from `index.md` (the value is inherited again). */
  clear?: ContainerKey[]
}

/** Is `data` an answer of GET /api/backlog/containers/{id}? */
export function isContainerDetail(data: unknown): data is ContainerDetailData {
  if (typeof data !== 'object' || data === null) return false
  const c = (data as { container?: unknown }).container
  if (typeof c !== 'object' || c === null) return false
  const v = c as Record<string, unknown>
  return (
    typeof v.id === 'string' &&
    typeof v.own === 'object' &&
    v.own !== null &&
    typeof v.effective === 'object' &&
    v.effective !== null
  )
}

export function fetchContainer(containerId: string): Promise<ContainerDetailData> {
  return getApi<ContainerDetailData>(containerPath(containerId))
}

export function addContainer(input: AddContainerInput): Promise<ContainerWriteResult> {
  return postApi<ContainerWriteResult>('/backlog/containers', input)
}

export function editContainer(
  containerId: string,
  input: EditContainerInput,
): Promise<ContainerWriteResult> {
  return postApi<ContainerWriteResult>(`${containerPath(containerId)}/edit`, input)
}

/** A setting value for text: a list joined by commas, a flag as zapnuto/vypnuto. */
export function settingText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'zapnuto' : 'vypnuto'
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : '(prázdné)'
  return String(value)
}

/** Where an inherited value comes from: `Projekt M01`, `.factory/config.yaml (docs_dir)`. */
export function originText(origin: SettingOrigin | null | undefined): string {
  if (!origin) return 'nenastaveno'
  if (origin.source === 'config') return `${origin.path} (${origin.key})`
  if (origin.source === 'default') return 'výchozí'
  const label = levelLabel(origin.level)
  return origin.id ? `${label} ${origin.id}` : label
}

/**
 * The level a new container under `parent` gets: the top level without a parent, the next
 * container level under it; null when `parent` holds tasks only (the last container level).
 */
export function childLevel(levels: readonly string[], parentLevel?: string | null): string | null {
  const containers = levels.slice(0, -1)
  if (!parentLevel) return containers[0] ?? null
  const at = containers.indexOf(parentLevel)
  if (at < 0 || at + 1 >= containers.length) return null
  return containers[at + 1] ?? null
}

/** Czech labels of the task and container settings (the key stays visible next to them). */
export const SETTING_LABELS: Record<string, string> = {
  harness: 'Harness',
  model: 'Model',
  thinking: 'Přemýšlení',
  workflow: 'Workflow',
  writes: 'Zápisy',
  test_timeout: 'Limit testů (s)',
  source: 'Zdroj',
  target: 'Cíl',
  specs_dir: 'Adresář specifikací',
  docs_dir: 'Adresář dokumentace',
  workdir: 'Pracovní adresář agentů',
  auto_continue: 'Auto continue',
  auto_merge: 'Auto-merge',
}

/** Options of an inherited switch, the same labels everywhere. */
export const INHERIT_LABEL = 'Zděděno'

// ── Codes of new projects and steps ─────────────────────────────────────────

/** Ids of the containers directly under `parent` (the top level without one). */
export function childContainerIds(items: readonly BacklogNode[] | undefined, parent: string | null): string[] {
  const walk = (nodes: readonly BacklogNode[]): string[] | null => {
    for (const node of nodes) {
      if (node.kind !== 'container') continue
      if (node.id === parent) return childIds(node.children)
      const found = Array.isArray(node.children) ? walk(node.children) : null
      if (found) return found
    }
    return null
  }
  const childIds = (nodes: readonly BacklogNode[] | undefined) =>
    (Array.isArray(nodes) ? nodes : [])
      .filter((n): n is ContainerNode => n.kind === 'container' && !!n.id)
      .map((n) => n.id as string)
  if (!Array.isArray(items)) return []
  return parent === null ? childIds(items) : (walk(items) ?? [])
}

/** A short code of a new container or task: letters, digits, '.' and '_', without '-'. */
export const CODE_RE = /^[A-Za-z0-9][A-Za-z0-9._]*$/

/** The short code typed for a node under `parent`; a code carrying the parent's prefix loses it. */
export function shortCode(parent: string | null, code: string): string {
  const value = code.trim()
  return parent && value.startsWith(`${parent}-`) ? value.slice(parent.length + 1) : value
}

/** The full id the server composes from a short code: `S10` under `HAIFA` is `HAIFA-S10`. */
export function composeId(parent: string | null, code: string): string {
  const local = shortCode(parent, code)
  return parent ? `${parent}-${local}` : local
}

/**
 * The short code to suggest for a new container: the next number after the codes of its
 * siblings (`S02` after `HAIFA-S01`), else the first letter of the level with 01
 * (`P01` for a project, `S01` for a step).
 */
export function suggestContainerCode(level: string, parent: string | null, siblings: readonly string[]): string {
  const prefix = parent ? `${parent}-` : ''
  let best: { head: string; n: number; width: number } | null = null
  for (const id of siblings) {
    const local = parent && id.startsWith(prefix) ? id.slice(prefix.length) : parent ? null : id
    const m = local ? /^(.*?)(\d+)$/.exec(local) : null
    if (!m) continue
    const n = Number(m[2])
    if (!best || n > best.n) best = { head: m[1] ?? '', n, width: (m[2] ?? '').length }
  }
  if (best) return `${best.head}${String(best.n + 1).padStart(best.width, '0')}`
  const letter = (levelLabel(level).trim()[0] ?? 'X').toUpperCase()
  return `${letter}01`
}

/** The next free task code of a step (`T05` after `<step>-T04`), as the server picks it. */
export function suggestTaskCode(step: string, taskIds: readonly string[]): string {
  const prefix = `${step}-T`
  let n = 0
  let width = 2
  for (const id of taskIds) {
    const digits = id.startsWith(prefix) ? id.slice(prefix.length) : ''
    if (!/^\d+$/.test(digits)) continue
    n = Math.max(n, Number(digits))
    width = Math.max(width, digits.length)
  }
  return `T${String(n + 1).padStart(width, '0')}`
}

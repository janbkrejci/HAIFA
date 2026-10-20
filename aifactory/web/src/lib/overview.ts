// The overview (#/overview): what runs, waits for review and failed in every registered repo.
// Pure helpers (urgency, totals, filter, links) and useOverview, which polls GET /api/overview
// every 2 s while the tab is visible, reloads on focus and on demand; it never writes.
import { onScopeDispose, ref, type Ref } from 'vue'
import {
  fetchOverview,
  type OverviewData,
  type OverviewFailed,
  type OverviewRepo,
  type OverviewReview,
  type OverviewRunning,
} from './api'
import { BOARD_STATES, STATE_LABELS, type BoardState } from './backlog'
import { repoHref } from './router'
import { errorText, plural } from './format'
import { failureLabel } from './failure'

export const OVERVIEW_POLL_MS = 2000

/** The totals at the top; a click on one filters the cards. */
export type OverviewFilter = 'running' | 'review' | 'automerge' | 'failed' | 'problems'

export const TOTALS: readonly { id: OverviewFilter; label: string }[] = [
  { id: 'running', label: 'Běží' },
  { id: 'review', label: 'Čeká na review' },
  { id: 'automerge', label: 'Čeká na automerge PR' },
  { id: 'failed', label: 'Selhalo' },
  { id: 'problems', label: 'Problémy' },
]

/** Urgency of a repo card, most urgent first. A PR waiting for auto-merge needs nobody, so it
 * ranks after running runs: the factory still works on the repo, but the user need not. */
export type Urgency = 'problems' | 'failed' | 'review' | 'running' | 'automerge' | 'calm'
const URGENCY_ORDER: readonly Urgency[] = ['problems', 'failed', 'review', 'running', 'automerge', 'calm']

/** The text a run whose process is gone shows. */
export const PROCESS_ENDED = 'proces skončil'

/** A row of the Selhalo section: a failed task or a running row whose process ended. */
export interface FailedRow {
  run_id: string
  task_id: string
  task_title: string | null
  error: string | null
  /** "proces skončil" for a running row without its process, else the failure kind in Czech. */
  label: string | null
}

/** A problem of a repo: its configuration (links to the repo settings) or its folder. */
export interface Problem {
  kind: 'not_installed' | 'invalid' | 'uncommitted' | 'missing' | 'not_git' | 'timeout' | 'error'
  text: string
  /** The repo settings for a configuration problem, null otherwise. */
  href: string | null
}

const STATE_PROBLEMS: Partial<Record<OverviewRepo['state'], Problem['kind']>> = {
  missing: 'missing',
  not_git: 'not_git',
  timeout: 'timeout',
  error: 'error',
}

const PROBLEM_TEXT: Record<Problem['kind'], string> = {
  not_installed: 'Nenainstalováno',
  invalid: 'Neplatná konfigurace',
  uncommitted: 'Necommitnutá konfigurace',
  missing: 'Složka nenalezena',
  not_git: 'Není git repozitář',
  timeout: 'Repo neodpovědělo včas',
  error: 'Repo se nepodařilo přečíst',
}

/** Open PRs the factory merges by itself (older responses have no list). */
export function automergePrs(repo: OverviewRepo): OverviewReview[] {
  return repo.automerge ?? []
}

/** Runs that still run (a run whose process ended counts as failed). */
export function activeRuns(repo: OverviewRepo): OverviewRunning[] {
  return repo.running.filter((r) => r.process !== 'ended')
}

/** Failed tasks plus running rows whose process is gone. */
export function failedRows(repo: OverviewRepo): FailedRow[] {
  const ended = repo.running
    .filter((r) => r.process === 'ended')
    .map((r) => ({
      run_id: r.run_id,
      task_id: r.task_id,
      task_title: r.task_title,
      error: null,
      label: r.status_label ?? PROCESS_ENDED,
    }))
  const failed = repo.failed.map((f: OverviewFailed) => ({
    run_id: f.run_id,
    task_id: f.task_id,
    task_title: f.task_title,
    error: f.error,
    label: failureLabel(f.failure_kind) || null,
  }))
  return [...ended, ...failed]
}

/** The problems of a repo: a missing or unreadable folder, or its configuration. */
export function problems(repo: OverviewRepo): Problem[] {
  const stateKind = STATE_PROBLEMS[repo.state]
  if (stateKind) return [{ kind: stateKind, text: PROBLEM_TEXT[stateKind], href: null }]
  // the configuration is installed, fixed and committed on the Factory screen
  const factory = repoHref(repo.id, 'factory')
  const commit = repoHref(repo.id, 'factory', 'config_commit')
  const kinds: Problem['kind'][] = []
  const config = repo.config
  if (config) {
    if (!config.installed) kinds.push('not_installed')
    if (config.invalid) kinds.push('invalid')
    if (config.uncommitted.length > 0 || config.factory_state === 'uncommitted') kinds.push('uncommitted')
  } else if (repo.state === 'not_installed') kinds.push('not_installed')
  else if (repo.state === 'invalid_config') kinds.push('invalid')
  else if (repo.state === 'uncommitted') kinds.push('uncommitted')
  return kinds.map((kind) => ({ kind, text: PROBLEM_TEXT[kind], href: kind === 'uncommitted' ? commit : factory }))
}

/** Whether the repo has a problem: a state or config problem, or warnings. */
export function hasProblems(repo: OverviewRepo): boolean {
  return problems(repo).length > 0 || repo.warnings.length > 0
}

export function urgency(repo: OverviewRepo): Urgency {
  if (hasProblems(repo)) return 'problems'
  if (failedRows(repo).length > 0) return 'failed'
  if (repo.review.length > 0) return 'review'
  if (activeRuns(repo).length > 0) return 'running'
  // a stop still on its way keeps the card (and its progress) in sight
  if ((repo.factory?.control?.pending.length ?? 0) > 0) return 'running'
  if (automergePrs(repo).length > 0) return 'automerge'
  return 'calm'
}

/** One chip of the task summary: a board state with its count. */
/** The class that colours a state chip (`state-in-review`); the colours are in style.css under
 * `.state-chip`, shared by the backlog StateChip and the overview task summary. */
export function stateClass(state: BoardState): string {
  return `state-${state.replace(/\s+/g, '-')}`
}

export interface TaskSummaryItem {
  state: BoardState
  label: string
  count: number
}

/** The tasks of a repo per board state, in kanban order; states without a task are left out. */
export function taskSummary(repo: Pick<OverviewRepo, 'tasks'>): TaskSummaryItem[] {
  const tasks = repo.tasks
  if (!tasks) return []
  return BOARD_STATES.filter((state) => (tasks[state] ?? 0) > 0).map((state) => ({
    state,
    label: STATE_LABELS[state],
    count: tasks[state],
  }))
}

export const BY_PROJECT_KEY = 'haifa.overview.byProject'

export function readByProject(): boolean {
  try {
    return typeof localStorage === 'undefined' || localStorage.getItem(BY_PROJECT_KEY) !== '0'
  } catch {
    return true
  }
}

export function writeByProject(on: boolean): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(BY_PROJECT_KEY, on ? '1' : '0')
  } catch {
    // The switch still works when browser storage is unavailable.
  }
}

/** Project slices keep repo identity for links; only work lists and task counts change. */
export function projectSections(repo: OverviewRepo): { id: string | null; title: string; repo: OverviewRepo }[] {
  const projects = repo.projects ?? []
  const ids = new Set(projects.map((p) => p.id))
  const sections: { id: string | null; title: string; tasks: OverviewRepo['tasks'] }[] =
    projects.map((p) => ({ id: p.id, title: p.title, tasks: p.tasks }))
  const lists = [repo.running, repo.review, repo.automerge ?? [], repo.failed]
  if (lists.some((rows) => rows.some((row) => row.project == null || !ids.has(row.project)))) {
    sections.push({ id: null, title: 'Bez projektu', tasks: null })
  }
  return sections.map(({ id, title, tasks }) => {
    const belongs = (row: { project?: string | null }) =>
      id === null ? row.project == null || !ids.has(row.project) : row.project === id
    return {
      id, title,
      repo: { ...repo, tasks, running: repo.running.filter(belongs), review: repo.review.filter(belongs),
        automerge: (repo.automerge ?? []).filter(belongs), failed: repo.failed.filter(belongs) },
    }
  })
}

/** Spustit továrnu: a ready task and a free parallel slot. */
export function canStart(repo: OverviewRepo): boolean {
  return repo.factory?.can_start === true
}

/** Pauza: a running run without a pause. */
export function canPause(repo: OverviewRepo): boolean {
  return activeRuns(repo).some((r) => !r.pause)
}

/** Pokračovat: a run that pauses or is paused. */
export function canResume(repo: OverviewRepo): boolean {
  return activeRuns(repo).some((r) => r.pause === 'pausing' || r.pause === 'paused')
}

/** Stop: anything running. */
export function canStop(repo: OverviewRepo): boolean {
  return activeRuns(repo).length > 0
}

/** "dobíhá 1 běh", "dobíhají 2 běhy", "dobíhá 5 běhů". */
export function runsFinishing(n: number): string {
  return `${plural(n, 'dobíhá', 'dobíhají', 'dobíhá')} ${n} ${plural(n, 'běh', 'běhy', 'běhů')}`
}

/** The state of a stop or pause of the whole repo. */
export interface ControlStatus {
  kind: 'stopping' | 'stopped' | 'pausing' | 'paused'
  text: string
}

export function controlStatus(repo: OverviewRepo): ControlStatus | null {
  const control = repo.factory?.control
  if (!control) return null
  if (control.action === 'stop') {
    const n = control.pending.length
    if (n > 0) return { kind: 'stopping', text: `Zastavuje se – ${runsFinishing(n)}` }
    return { kind: 'stopped', text: 'Zastaveno' }
  }
  const ids = new Set(control.run_ids)
  const affected = activeRuns(repo).filter((r) => ids.has(r.run_id))
  const left = affected.filter((r) => r.pause !== 'paused').length
  if (left > 0) return { kind: 'pausing', text: `Pozastavuje se – ${runsFinishing(left)}` }
  if (affected.length > 0) return { kind: 'paused', text: 'Pozastaveno' }
  return null
}

/** The errors of a stop of the whole repo, one line each. */
export function controlErrors(repo: OverviewRepo): string[] {
  return (repo.factory?.control?.errors ?? []).map(
    (e) => `Nepodařilo se: ${e.task_id ?? e.run_id} – ${e.message}`,
  )
}

/** Repos by urgency (problems, failures, review, running, auto-merge, calm), then by name. */
export function sortRepos(repos: readonly OverviewRepo[]): OverviewRepo[] {
  const rank = (r: OverviewRepo) => URGENCY_ORDER.indexOf(urgency(r))
  return [...repos].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, 'cs'))
}

/** Counts of a repo for the switcher. */
export interface RepoCounts {
  running: number
  review: number
  automerge: number
  failed: number
}

export function repoCounts(repo: OverviewRepo): RepoCounts {
  return {
    running: activeRuns(repo).length,
    review: repo.review.length,
    automerge: automergePrs(repo).length,
    failed: failedRows(repo).length,
  }
}

/** Counts of every repo by id. */
export function countsById(data: OverviewData | null): Record<string, RepoCounts> {
  const out: Record<string, RepoCounts> = {}
  for (const repo of data?.repos ?? []) out[repo.id] = repoCounts(repo)
  return out
}

/** The totals at the top: runs, PRs (review and auto-merge apart), failures, problem repos. */
export function totals(repos: readonly OverviewRepo[]): Record<OverviewFilter, number> {
  const sum = { running: 0, review: 0, automerge: 0, failed: 0, problems: 0 }
  for (const repo of repos) {
    const c = repoCounts(repo)
    sum.running += c.running
    sum.review += c.review
    sum.automerge += c.automerge
    sum.failed += c.failed
    if (hasProblems(repo)) sum.problems += 1
  }
  return sum
}

/** Whether a repo card shows under a total's filter (null shows all). */
export function matchesFilter(repo: OverviewRepo, filter: OverviewFilter | null): boolean {
  if (filter === null) return true
  if (filter === 'problems') return hasProblems(repo)
  return repoCounts(repo)[filter] > 0
}

export function runLink(repo: OverviewRepo, runId: string): string {
  return repoHref(repo.id, 'runs', runId)
}

export function reviewLink(repo: OverviewRepo, taskId: string): string {
  return repoHref(repo.id, 'review', taskId)
}

function hidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

export interface OverviewPoll {
  data: Ref<OverviewData | null>
  error: Ref<string | null>
  loading: Ref<boolean>
  refresh: () => Promise<void>
}

/**
 * GET /api/overview now, every `intervalMs` while the tab is visible, on a return to the
 * window or tab and on refresh(); stops with the calling scope.
 */
export function useOverview(intervalMs = OVERVIEW_POLL_MS): OverviewPoll {
  const data = ref<OverviewData | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)
  let generation = 0
  let timer: ReturnType<typeof setInterval> | undefined

  async function refresh(): Promise<void> {
    const mine = ++generation
    loading.value = true
    try {
      const next = await fetchOverview()
      if (mine !== generation) return
      data.value = next
      error.value = null
    } catch (err) {
      if (mine !== generation) return
      error.value = errorText(err)
    } finally {
      if (mine === generation) loading.value = false
    }
  }

  function stop() {
    if (timer !== undefined) clearInterval(timer)
    timer = undefined
  }

  function start() {
    stop()
    if (hidden()) return
    timer = setInterval(() => {
      if (!loading.value) void refresh()
    }, intervalMs)
  }

  function onVisibility() {
    if (hidden()) {
      stop()
    } else {
      void refresh()
      start()
    }
  }

  function onFocus() {
    void refresh()
  }

  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('focus', onFocus)
  void refresh()
  start()

  onScopeDispose(() => {
    stop()
    generation += 1
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('focus', onFocus)
  })

  return { data, error, loading, refresh }
}

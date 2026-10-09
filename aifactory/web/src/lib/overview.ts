// The overview (#/overview): what runs, waits for review and failed in every registered repo.
// Pure helpers (urgency, totals, filter, links) and useOverview, which polls GET /api/overview
// every 2 s while the tab is visible, reloads on focus and on demand; it never writes.
import { onScopeDispose, ref, type Ref } from 'vue'
import {
  fetchOverview,
  type OverviewData,
  type OverviewFailed,
  type OverviewRepo,
  type OverviewRunning,
} from './api'
import { repoHref } from './router'
import { errorText } from './format'

export const OVERVIEW_POLL_MS = 2000

/** The totals at the top; a click on one filters the cards. */
export type OverviewFilter = 'running' | 'review' | 'failed' | 'problems'

export const TOTALS: readonly { id: OverviewFilter; label: string }[] = [
  { id: 'running', label: 'Běží' },
  { id: 'review', label: 'Čeká na review' },
  { id: 'failed', label: 'Selhalo' },
  { id: 'problems', label: 'Problémy' },
]

/** Urgency of a repo card, most urgent first. */
export type Urgency = 'problems' | 'failed' | 'review' | 'running' | 'calm'
const URGENCY_ORDER: readonly Urgency[] = ['problems', 'failed', 'review', 'running', 'calm']

/** The text a run whose process is gone shows. */
export const PROCESS_ENDED = 'proces skončil'

/** A row of the Selhalo section: a failed task or a running row whose process ended. */
export interface FailedRow {
  run_id: string
  task_id: string
  task_title: string | null
  error: string | null
  /** "proces skončil" for a running row without its process. */
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
    label: null,
  }))
  return [...ended, ...failed]
}

/** The problems of a repo: a missing or unreadable folder, or its configuration. */
export function problems(repo: OverviewRepo): Problem[] {
  const stateKind = STATE_PROBLEMS[repo.state]
  if (stateKind) return [{ kind: stateKind, text: PROBLEM_TEXT[stateKind], href: null }]
  const settings = repoHref(repo.id, 'settings')
  const kinds: Problem['kind'][] = []
  const config = repo.config
  if (config) {
    if (!config.installed) kinds.push('not_installed')
    if (config.invalid) kinds.push('invalid')
    if (config.uncommitted.length > 0 || config.factory_state === 'working_tree') kinds.push('uncommitted')
  } else if (repo.state === 'not_installed') kinds.push('not_installed')
  else if (repo.state === 'invalid_config') kinds.push('invalid')
  else if (repo.state === 'uncommitted') kinds.push('uncommitted')
  return kinds.map((kind) => ({ kind, text: PROBLEM_TEXT[kind], href: settings }))
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
  return 'calm'
}

/** Repos by urgency (problems, failures, review, running, calm), then by name. */
export function sortRepos(repos: readonly OverviewRepo[]): OverviewRepo[] {
  const rank = (r: OverviewRepo) => URGENCY_ORDER.indexOf(urgency(r))
  return [...repos].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, 'cs'))
}

/** Counts of a repo for the switcher. */
export interface RepoCounts {
  running: number
  review: number
  failed: number
}

export function repoCounts(repo: OverviewRepo): RepoCounts {
  return { running: activeRuns(repo).length, review: repo.review.length, failed: failedRows(repo).length }
}

/** Counts of every repo by id. */
export function countsById(data: OverviewData | null): Record<string, RepoCounts> {
  const out: Record<string, RepoCounts> = {}
  for (const repo of data?.repos ?? []) out[repo.id] = repoCounts(repo)
  return out
}

/** The totals at the top: runs, PRs and failures, and repos with problems. */
export function totals(repos: readonly OverviewRepo[]): Record<OverviewFilter, number> {
  const sum = { running: 0, review: 0, failed: 0, problems: 0 }
  for (const repo of repos) {
    const c = repoCounts(repo)
    sum.running += c.running
    sum.review += c.review
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

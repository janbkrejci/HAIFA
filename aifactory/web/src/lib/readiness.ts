import { t } from './i18n'
import { inject, onBeforeUnmount, onMounted, provide, ref, computed, type InjectionKey } from 'vue'
import { ApiError, READ_TIMEOUT_MS, fetchFactoryRosterSummary, fetchMachineCheck, fetchRepos, getGlobal, type MachineCheck, type RepoItem } from './api'
import { fetchLibrarySummary } from './library'
import { focusRepo, gettingStartedSteps, type Step } from './gettingStarted'
import { CHECK_DEADLINE_MS, CheckTimeout, beforeDeadline, followProgress, lastKnown, serverStep, type CheckStep, type CheckStepId } from './machineProgress'
import { LIBRARY_HREF, SETUP_HREF, repoHref } from './router'
import { findingTitle, dashboardError } from './dashboardMessages'

/** `retry`: the issue's action explicitly runs a full machine check. */
type Issue = Pick<Step, 'title' | 'hint' | 'href' | 'action'> & { id: Step['id'] | 'timeout' | 'machine-status'; repo?: RepoItem; retry?: boolean; diagnostics?: string }
/** The requests the readiness waits for, in the words shown while it waits. */
const STEPS = { get machine() { return t('dashboard.machineStep') }, get library() { return t('dashboard.libraryStep') }, get repos() { return t('dashboard.reposStep') }, roster: 'roster', backlog: 'backlog' } as const
type StepKey = Exclude<CheckStepId, 'evaluation'>
function stepLabel(step: CheckStep): string {
  const label = step.id === 'evaluation' ? t('dashboard.evaluate') : STEPS[step.id]
  return step.detail ? `${label}: ${step.detail}` : label
}

function timeoutIssue(step: CheckStep, seconds: number, checkedAt: string | null | undefined): Issue {
  const known = () => lastKnown(checkedAt)
  return {
    id: 'timeout',
    get title() { return t('dashboard.checkTimeout', { seconds }) },
    get hint() { return t('dashboard.unfinishedStep', { step: stepLabel(step) }) + (known() ? t('dashboard.lastResult', { known: known()! }) : t('dashboard.noPrevious')) },
    href: SETUP_HREF,
    get action() { return t('dashboard.checkAgain') },
    retry: true,
  }
}

function createReadiness() {
  const phase = ref<'loading' | 'checking' | 'warning' | 'success' | null>(null)
  const issues = ref<Issue[]>([])
  /** What the running check waits for (with the server's step of the machine check). */
  const stepSource = ref<CheckStep | null>(null)
  const step = computed(() => stepSource.value ? stepLabel(stepSource.value) : null)
  /** Seconds since the running check started. */
  const elapsed = ref(0)
  let checking = false
  let manualRunning = false
  let generation = 0
  let disposed = false
  let loadingTimer: ReturnType<typeof setTimeout> | undefined
  let stopProgress: (() => void) | undefined
  let lastCheckedAt: string | null = null
  async function check(fresh = false, manual = false) {
    if (disposed || (checking && !manual) || (manual && manualRunning)) return
    const current = ++generation
    checking = true
    manualRunning = manual
    clearTimeout(loadingTimer)
    if (manual) phase.value = 'checking'
    else if (phase.value === null) {
      loadingTimer = setTimeout(() => { phase.value = 'loading' }, 1000)
    }
    let finished = false
    let machineDone = false
    let failedStep: StepKey | null = null
    const pending = new Set<StepKey>()
    let server: string | null = null
    const waitingFor = (): CheckStep => {
      const first = [...pending][0]
      if (!first) return { id: 'evaluation' }
      return { id: first, ...(first === 'machine' && server ? { detail: server } : {}) }
    }
    function track<T>(key: StepKey, promise: Promise<T>): Promise<T> {
      pending.add(key)
      return promise.catch(error => {
        failedStep ??= key
        if (error instanceof ApiError && error.code === 'request_timeout') {
          throw new CheckTimeout({ id: key }, READ_TIMEOUT_MS / 1000)
        }
        throw error
      }).finally(() => pending.delete(key))
    }
    stopProgress?.()
    elapsed.value = 0
    stepSource.value = null
    stopProgress = followProgress((seconds, serverStepText) => {
      if (current !== generation) return
      server = serverStepText
      elapsed.value = seconds
      stepSource.value = waitingFor()
    }, () => pending.has('machine'))
    const deadline = Date.now() + CHECK_DEADLINE_MS
    const seconds = Math.round(CHECK_DEADLINE_MS / 1000)
    const bounded = <T>(promise: Promise<T>) => beforeDeadline(promise, deadline, waitingFor, seconds)
    try {
      const initial = await bounded(Promise.allSettled([
        track('machine', fetchMachineCheck(fresh).then(machine => {
          if (!finished && !disposed && current === generation) {
            machineDone = !machine.timed_out && machine.checked !== false
            if (machineDone && machine.checked_at) lastCheckedAt = machine.checked_at
            issues.value = machineIssues(machine)
          }
          return machine
        })), track('library', fetchLibrarySummary()), track('repos', fetchRepos()),
      ]))
      if (disposed || current !== generation) return
      const [machineResult, libraryResult, registryResult] = initial
      if (machineResult.status === 'rejected') throw machineResult.reason
      if (libraryResult.status === 'rejected') throw libraryResult.reason
      if (registryResult.status === 'rejected') throw registryResult.reason
      const machine = machineResult.value
      const library = libraryResult.value
      const registry = registryResult.value
      const repo = focusRepo(registry.repos)
      let rosterAgents = 0
      let projects = 0
      if (repo && ['ok', 'uncommitted'].includes(repo.status)) {
        const [roster, backlog] = await bounded(Promise.all([
          track('roster', fetchFactoryRosterSummary(repo.id)),
          track('backlog', getGlobal<{ projects: number }>(`/repos/${encodeURIComponent(repo.id)}/backlog/summary`)),
        ]))
        rosterAgents = roster.agents
        projects = backlog.projects
      }
      if (disposed || current !== generation) return
      const timedOut = machineTimeout(machine)
      if (!timedOut && machine.checked_at) lastCheckedAt = machine.checked_at
      const unknown = machine.checked === false
      const outdated = unknown || machine.stale
      const machineErrors = machine.findings.filter(f => f.severity === 'error' || f.severity === 'warning')
      issues.value = gettingStartedSteps({ check: machine, library, repos: registry.repos, rosterAgents, projects }).filter(step => {
        if (step.id === 'machine' && (machineErrors.length || timedOut || outdated)) return false
        if (step.id === 'factory' && registry.repos.some(r => r.status !== 'ok')) return false
        if (step.id === 'roster' && rosterAgents > 0) return false
        return !step.done
      })
      if (timedOut) issues.value.unshift(timedOut)
      else if (outdated) issues.value.unshift({
        id: 'machine-status', get title() { return unknown ? t('dashboard.unchecked') : t('dashboard.staleCheck') },
        get hint() { return t('dashboard.manualCheckHint') }, href: SETUP_HREF,
        get action() { return t('dashboard.checkMachine') }, retry: true,
      })
      for (const finding of machineErrors) {
      issues.value.push({ id: 'machine', get title() { return timedOut ? t('dashboard.lastKnownFinding', { message: findingTitle(finding.code) }) : findingTitle(finding.code) }, get hint() { return t('dashboard.fixHint') }, diagnostics: [finding.message, finding.fix].filter(Boolean).join('\n'), href: finding.code === 'harness_test_failed' ? '#harness-settings' : finding.scope === 'library' ? LIBRARY_HREF : SETUP_HREF, get action() { return finding.code === 'harness_test_failed' ? t('dashboard.configureHarnesses') : t('dashboard.fixComputer') } })
      }
      for (const item of registry.repos.filter(r => r.status !== 'ok')) {
        const uncommitted = item.status === 'uncommitted'
        const unavailable = ['missing', 'not_git'].includes(item.status)
        issues.value.push({ id: 'factory', get title() { return `${item.name}: ${item.status === 'uncommitted' ? t('dashboard.uncommittedConfig') : item.status === 'missing' ? t('dashboard.missingFolder') : item.status === 'not_git' ? t('dashboard.notGit') : t('dashboard.notInstalled')}` }, get hint() { return uncommitted ? t('dashboard.commitHint') : unavailable ? t('dashboard.invalidRepoHint') : t('dashboard.installRepoHint') }, href: repoHref(item.id, 'factory', ...(uncommitted ? ['config_commit'] : [])), get action() { return uncommitted ? t('dashboard.commitConfig') : unavailable ? t('dashboard.removeDashboard') : t('dashboard.installFactory') }, ...(unavailable ? { repo: item } : {}) })
      }
      if (issues.value.length) phase.value = 'warning'
      else phase.value = 'success'
    } catch (error) {
      if (!disposed && current === generation) {
        if (error instanceof CheckTimeout) {
          // Keep the last known issues next to the timeout; a timeout is never a success.
          issues.value = [machineDone ? auxiliaryIssue(error.step) : timeoutIssue(error.step, error.seconds, lastCheckedAt), ...issues.value.filter(i => i.id !== 'timeout')]
        } else {
          issues.value = machineDone
            ? [auxiliaryIssue({ id: failedStep ?? 'machine' }, error), ...issues.value.filter(i => i.id !== 'timeout')]
            : [{ id: 'machine', get title() { return t('dashboard.checkFailed') }, get hint() { return dashboardError(error) }, href: SETUP_HREF, get action() { return t('dashboard.openLibrary') } }]
        }
        phase.value = 'warning'
      }
    } finally {
      finished = true
      if (current === generation) {
        clearTimeout(loadingTimer)
        stopProgress?.()
        stopProgress = undefined
        checking = false
        manualRunning = false
        stepSource.value = null
        elapsed.value = 0
      }
    }
  }

  function auxiliaryIssue(step: CheckStep, error?: unknown): Issue {
    const known = () => lastKnown(lastCheckedAt)
    return {
      id: 'timeout', get title() { return t('dashboard.unavailableStep', { step: stepLabel(step) }) },
      get hint() { return t('dashboard.unfinishedStep', { step: stepLabel(step) }) + (known() ? t('dashboard.lastResultSpace', { known: known()! }) : '') + (error === undefined ? '' : dashboardError(error)) },
      href: SETUP_HREF, get action() { return t('dashboard.checkAgain') }, retry: true,
    }
  }

  function machineIssues(machine: MachineCheck): Issue[] {
    const result: Issue[] = machine.findings.filter(f => f.severity === 'error' || f.severity === 'warning').map(f => ({
      id: 'machine', get title() { return findingTitle(f.code) }, get hint() { return t('dashboard.fixHint') }, diagnostics: [f.message, f.fix].filter(Boolean).join('\n'),
      href: f.code === 'harness_test_failed' ? '#harness-settings' : f.scope === 'library' ? LIBRARY_HREF : SETUP_HREF,
      get action() { return f.code === 'harness_test_failed' ? t('dashboard.configureHarnesses') : t('dashboard.fixComputer') },
    }))
    const timeout = machineTimeout(machine)
    if (timeout) result.unshift(timeout)
    else if (machine.checked === false || machine.stale) result.unshift({
      id: 'machine-status', get title() { return machine.checked === false ? t('dashboard.unchecked') : t('dashboard.staleCheck') },
      get hint() { return t('dashboard.manualCheckHint') }, href: SETUP_HREF, get action() { return t('dashboard.checkMachine') }, retry: true,
    })
    return result
  }

  /** The issue of a machine check the server ended at its budget, or null. */
  function machineTimeout(machine: MachineCheck): Issue | null {
    if (!machine.timed_out) return null
    const budget = machine.progress?.budget ?? Math.round(CHECK_DEADLINE_MS / 1000)
    const detail = serverStep(machine.progress)
    return timeoutIssue({ id: 'machine', ...(detail ? { detail } : {}) }, budget, machine.checked_at)
  }

  // The server checks once at start; a page load reads that result, later checks are explicit.
  function recheck() { void check(true, true) }
  function refresh(fresh = false) { void check(fresh) }
  function onFactoryApplied() { refresh() }
  onMounted(() => { refresh(); window.addEventListener('factory-applied', onFactoryApplied) })
  onBeforeUnmount(() => { disposed = true; clearTimeout(loadingTimer); stopProgress?.(); window.removeEventListener('factory-applied', onFactoryApplied) })
  return { phase, issues, step, elapsed, recheck, refresh }
}
const key: InjectionKey<ReturnType<typeof createReadiness>> = Symbol('readiness')
export function provideReadiness() {
  const state = createReadiness()
  provide(key, state)
  return state
}
export function useReadiness() { return inject(key, null) ?? createReadiness() }

import { inject, onBeforeUnmount, onMounted, provide, ref, type InjectionKey } from 'vue'
import { fetchFactoryRosterSummary, fetchMachineCheck, fetchRepos, getGlobal, type MachineCheck, type RepoItem } from './api'
import { fetchLibrarySummary } from './library'
import { focusRepo, gettingStartedSteps, type Step } from './gettingStarted'
import { errorText } from './format'
import { CHECK_DEADLINE_MS, CheckTimeout, beforeDeadline, followProgress, lastKnown, serverStep } from './machineProgress'
import { LIBRARY_HREF, SETUP_HREF, repoHref } from './router'
import { repoStatusText } from './repos'

/** `retry`: the issue's action explicitly runs a full machine check. */
type Issue = Pick<Step, 'title' | 'hint' | 'href' | 'action'> & { id: Step['id'] | 'timeout' | 'machine-status'; repo?: RepoItem; retry?: boolean }
/** The requests the readiness waits for, in the words shown while it waits. */
const STEPS = { machine: 'kontrola počítače', library: 'stav knihovny', repos: 'seznam repozitářů', roster: 'roster', backlog: 'backlog' } as const
type StepKey = keyof typeof STEPS

function timeoutIssue(step: string, seconds: number, checkedAt: string | null | undefined): Issue {
  const known = lastKnown(checkedAt)
  return {
    id: 'timeout',
    title: `Kontrola nedoběhla do ${seconds} s`,
    hint: `Nedokončený krok: ${step}. ` + (known ? `Zobrazen poslední známý výsledek ${known}.` : 'Dřívější výsledek není k dispozici.'),
    href: SETUP_HREF,
    action: 'Zkontrolovat znovu',
    retry: true,
  }
}

function createReadiness() {
  const phase = ref<'loading' | 'checking' | 'warning' | 'success' | null>(null)
  const issues = ref<Issue[]>([])
  /** What the running check waits for (with the server's step of the machine check). */
  const step = ref<string | null>(null)
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
    const waitingFor = () => {
      const first = [...pending][0]
      if (!first) return 'vyhodnocení'
      return first === 'machine' && server ? `${STEPS.machine}: ${server}` : STEPS[first]
    }
    function track<T>(key: StepKey, promise: Promise<T>): Promise<T> {
      pending.add(key)
      return promise.catch(error => { failedStep ??= key; throw error }).finally(() => pending.delete(key))
    }
    stopProgress?.()
    elapsed.value = 0
    step.value = null
    stopProgress = followProgress((seconds, serverStepText) => {
      if (current !== generation) return
      server = serverStepText
      elapsed.value = seconds
      step.value = waitingFor()
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
        id: 'machine-status', title: unknown ? 'Počítač zatím nebyl zkontrolován' : 'Zastaralý výsledek kontroly počítače',
        hint: 'Spusť ruční kontrolu pro aktuální stav počítače.', href: SETUP_HREF,
        action: 'Zkontrolovat počítač', retry: true,
      })
      for (const finding of machineErrors) {
      issues.value.push({ id: 'machine', title: timedOut ? `${finding.message} (poslední známý stav)` : finding.message, hint: finding.fix ?? 'Otevři stránku Knihovna a oprav uvedený problém.', href: finding.code === 'harness_test_failed' ? '#harness-settings' : finding.scope === 'library' ? LIBRARY_HREF : SETUP_HREF, action: finding.code === 'harness_test_failed' ? 'Nastavit a testovat harnessy' : 'Opravit na tomto počítači' })
      }
      for (const item of registry.repos.filter(r => r.status !== 'ok')) {
        const uncommitted = item.status === 'uncommitted'
        const unavailable = ['missing', 'not_git'].includes(item.status)
        issues.value.push({ id: 'factory', title: `${item.name}: ${repoStatusText(item.status)}`, hint: uncommitted ? 'Commitni změny konfigurace, aby je běhy mohly používat.' : unavailable ? 'Odeber neplatný záznam a přidej správnou složku repozitáře.' : 'Nainstaluj factory v repozitáři.', href: repoHref(item.id, 'factory', ...(uncommitted ? ['config_commit'] : [])), action: uncommitted ? 'Commitnout konfiguraci' : unavailable ? 'Odebrat z dashboardu' : 'Nainstalovat factory', ...(unavailable ? { repo: item } : {}) })
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
            ? [auxiliaryIssue(STEPS[failedStep ?? 'machine'], errorText(error)), ...issues.value.filter(i => i.id !== 'timeout')]
            : [{ id: 'machine', title: 'Kontrolu se nepodařilo dokončit.', hint: errorText(error), href: SETUP_HREF, action: 'Otevřít stránku Knihovna' }]
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
        step.value = null
        elapsed.value = 0
      }
    }
  }

  function auxiliaryIssue(step: string, error?: string): Issue {
    const known = lastKnown(lastCheckedAt)
    return {
      id: 'timeout', title: `Údaj není k dispozici: ${step}`,
      hint: `Nedokončený krok: ${step}. ` + (known ? `Zobrazen poslední známý výsledek ${known}. ` : '') + (error ?? ''),
      href: SETUP_HREF, action: 'Zkontrolovat znovu', retry: true,
    }
  }

  function machineIssues(machine: MachineCheck): Issue[] {
    const result: Issue[] = machine.findings.filter(f => f.severity === 'error' || f.severity === 'warning').map(f => ({
      id: 'machine', title: f.message, hint: f.fix ?? 'Otevři stránku Knihovna a oprav uvedený problém.',
      href: f.code === 'harness_test_failed' ? '#harness-settings' : f.scope === 'library' ? LIBRARY_HREF : SETUP_HREF,
      action: f.code === 'harness_test_failed' ? 'Nastavit a testovat harnessy' : 'Opravit na tomto počítači',
    }))
    const timeout = machineTimeout(machine)
    if (timeout) result.unshift(timeout)
    else if (machine.checked === false || machine.stale) result.unshift({
      id: 'machine-status', title: machine.checked === false ? 'Počítač zatím nebyl zkontrolován' : 'Zastaralý výsledek kontroly počítače',
      hint: 'Spusť ruční kontrolu pro aktuální stav počítače.', href: SETUP_HREF, action: 'Zkontrolovat počítač', retry: true,
    })
    return result
  }

  /** The issue of a machine check the server ended at its budget, or null. */
  function machineTimeout(machine: MachineCheck): Issue | null {
    if (!machine.timed_out) return null
    const budget = machine.progress?.budget ?? Math.round(CHECK_DEADLINE_MS / 1000)
    const unfinished = serverStep(machine.progress) ?? STEPS.machine
    return timeoutIssue(`${STEPS.machine}: ${unfinished}`, budget, machine.checked_at)
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

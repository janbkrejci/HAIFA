import { inject, onBeforeUnmount, onMounted, provide, ref, type InjectionKey } from 'vue'
import { fetchFactoryRoster, fetchMachineCheck, fetchRepos, getGlobal, type RepoItem } from './api'
import { fetchLibrarySummary } from './library'
import { focusRepo, gettingStartedSteps, type Step } from './gettingStarted'
import { errorText } from './format'
import { LIBRARY_HREF, SETUP_HREF, repoHref } from './router'
import { repoStatusText } from './repos'

type Issue = Pick<Step, 'id' | 'title' | 'hint' | 'href' | 'action'> & { repo?: RepoItem }
function createReadiness() {
  const phase = ref<'checking' | 'warning' | 'success' | null>(null)
  const issues = ref<Issue[]>([])
  let checking = false
  let generation = 0
  let disposed = false
  let loadingTimer: ReturnType<typeof setTimeout> | undefined
  async function check(fresh = false, manual = false) {
    if (disposed || (checking && !manual)) return
    const current = ++generation
    checking = true
    clearTimeout(loadingTimer)
    if (manual) phase.value = 'checking'
    else if (phase.value === null) {
      loadingTimer = setTimeout(() => { phase.value = 'checking' }, 1000)
    }
    try {
      const [machine, library, registry] = await Promise.all([
        fetchMachineCheck(fresh), fetchLibrarySummary(), fetchRepos(),
      ])
      if (disposed || current !== generation) return
      const repo = focusRepo(registry.repos)
      let rosterAgents = 0
      let projects = 0
      if (repo && ['ok', 'uncommitted'].includes(repo.status)) {
        const [roster, backlog] = await Promise.all([
          fetchFactoryRoster(repo.id),
          getGlobal<{ items?: unknown[] }>(`/repos/${encodeURIComponent(repo.id)}/backlog`),
        ])
        rosterAgents = roster.agents.length
        projects = backlog.items?.length ?? 0
      }
      if (disposed || current !== generation) return
      const machineErrors = machine.findings.filter(f => f.severity === 'error' || f.severity === 'warning')
      issues.value = gettingStartedSteps({ check: machine, library, repos: registry.repos, rosterAgents, projects }).filter(step => {
        if (step.id === 'machine' && machineErrors.length) return false
        if (step.id === 'factory' && registry.repos.some(r => r.status !== 'ok')) return false
        if (step.id === 'roster' && rosterAgents > 0) return false
        return !step.done
      })
      for (const finding of machineErrors) {
      issues.value.push({ id: 'machine', title: finding.message, hint: finding.fix ?? 'Otevři stránku Knihovna a oprav uvedený problém.', href: finding.code === 'harness_test_failed' ? '#harness-settings' : finding.scope === 'library' ? LIBRARY_HREF : SETUP_HREF, action: finding.code === 'harness_test_failed' ? 'Nastavit a testovat harnessy' : 'Opravit na tomto počítači' })
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
        issues.value = [{ id: 'machine', title: 'Kontrolu se nepodařilo dokončit.', hint: errorText(error), href: SETUP_HREF, action: 'Otevřít stránku Knihovna' }]
        phase.value = 'warning'
      }
    } finally {
      if (current === generation) { clearTimeout(loadingTimer); checking = false }
    }
  }

  // The server checks once at start; a page load reads that result, later checks are explicit.
  function recheck() { void check(true, true) }
  function refresh(fresh = false) { void check(fresh) }
  function onFactoryApplied() { refresh() }
  onMounted(() => { refresh(); window.addEventListener('factory-applied', onFactoryApplied) })
  onBeforeUnmount(() => { disposed = true; clearTimeout(loadingTimer); window.removeEventListener('factory-applied', onFactoryApplied) })
  return { phase, issues, recheck, refresh }
}
const key: InjectionKey<ReturnType<typeof createReadiness>> = Symbol('readiness')
export function provideReadiness() {
  const state = createReadiness()
  provide(key, state)
  return state
}
export function useReadiness() { return inject(key, null) ?? createReadiness() }

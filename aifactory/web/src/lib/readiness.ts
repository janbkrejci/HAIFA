import { inject, onBeforeUnmount, onMounted, provide, ref, type InjectionKey } from 'vue'
import { fetchFactoryRoster, fetchMachineCheck, fetchRepos, getGlobal, type RepoItem } from './api'
import { fetchLibrary } from './library'
import { focusRepo, gettingStartedSteps, type Step } from './gettingStarted'
import { errorText } from './format'
import { repoHref } from './router'
import { repoStatusText } from './repos'

type Issue = Pick<Step, 'id' | 'title' | 'hint' | 'href' | 'action'> & { repo?: RepoItem }
function createReadiness() {
  const phase = ref<'checking' | 'warning' | 'success'>('checking')
  const issues = ref<Issue[]>([])
  let checking = false
  let disposed = false
  let timer: ReturnType<typeof setInterval> | null = null
  async function check(fresh = false) {
    if (checking || disposed) return
    checking = true
    phase.value = 'checking'
    issues.value = []
    try {
      const [machine, library, registry] = await Promise.all([
        fetchMachineCheck(fresh), fetchLibrary(), fetchRepos(),
      ])
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
      if (disposed) return
      const machineErrors = machine.findings.filter(f => f.severity === 'error' || f.severity === 'warning')
      issues.value = gettingStartedSteps({ check: machine, library, repos: registry.repos, rosterAgents, projects }).filter(step => {
        if (step.id === 'machine' && machineErrors.length) return false
        if (step.id === 'factory' && registry.repos.some(r => r.status !== 'ok')) return false
        if (step.id === 'roster' && rosterAgents > 0) return false
        return !step.done
      })
      for (const finding of machineErrors) {
      issues.value.push({ id: 'machine', title: finding.message, hint: finding.fix ?? 'Otevři nastavení počítače a oprav uvedený problém.', href: finding.code === 'harness_test_failed' ? '#harness-settings' : '#/setup', action: finding.code === 'harness_test_failed' ? 'Nastavit a testovat harnessy' : 'Opravit na tomto počítači' })
      }
      for (const item of registry.repos.filter(r => r.status !== 'ok')) {
        const uncommitted = item.status === 'uncommitted'
        const unavailable = ['missing', 'not_git'].includes(item.status)
        issues.value.push({ id: 'factory', title: `${item.name}: ${repoStatusText(item.status)}`, hint: uncommitted ? 'Commitni změny konfigurace, aby je běhy mohly používat.' : unavailable ? 'Odeber neplatný záznam a přidej správnou složku repozitáře.' : 'Nainstaluj factory v repozitáři.', href: repoHref(item.id, 'factory', ...(uncommitted ? ['config_commit'] : [])), action: uncommitted ? 'Commitnout konfiguraci' : unavailable ? 'Odebrat z dashboardu' : 'Nainstalovat factory', ...(unavailable ? { repo: item } : {}) })
      }
      if (issues.value.length) phase.value = 'warning'
      else phase.value = 'success'
    } catch (error) {
      if (!disposed) {
        issues.value = [{ id: 'machine', title: 'Kontrolu se nepodařilo dokončit.', hint: errorText(error), href: '#/setup', action: 'Otevřít nastavení' }]
        phase.value = 'warning'
      }
    } finally { checking = false }
  }

  function recheck() { void check(true) }
  const readCached = () => { void check() }
  onMounted(() => { readCached(); timer = setInterval(readCached, 60_000); window.addEventListener('focus', readCached); window.addEventListener('factory-applied', recheck) })
  onBeforeUnmount(() => { disposed = true; if (timer) clearInterval(timer); window.removeEventListener('focus', readCached); window.removeEventListener('factory-applied', recheck) })
  return { phase, issues, recheck }
}
const key: InjectionKey<ReturnType<typeof createReadiness>> = Symbol('readiness')
export function provideReadiness() {
  const state = createReadiness()
  provide(key, state)
  return state
}
export function useReadiness() { return inject(key, null) ?? createReadiness() }

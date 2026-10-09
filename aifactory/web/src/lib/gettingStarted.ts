// The steps of the first visit (GettingStarted on the overview and on #/setup): from this machine
// to the first project of a backlog. Pure: the component loads the inputs, this decides the states.
import type { MachineCheck, RepoItem } from './api'
import type { LibraryStatus } from './library'
import { detectedHarnesses } from './roster'
import { NEW_CONTAINER, REPOS_ADD_HREF, repoHref } from './router'

export type StepId = 'machine' | 'library' | 'harnesses' | 'repo' | 'factory' | 'roster' | 'project'

export interface GettingStartedInput {
  check: MachineCheck | null
  library: LibraryStatus | null
  repos: RepoItem[] | null
  /** Agents in the roster of the focus repo; null when unknown. */
  rosterAgents: number | null
  /** Projects (top-level containers) in the backlog of the focus repo; null when unknown. */
  projects: number | null
}

export interface Step {
  id: StepId
  title: string
  done: boolean
  /** What the step needs, or what makes it done. */
  hint: string
  href: string
  action: string
}

/** The repo the later steps are about: the first installed one, else the first usable one. */
export function focusRepo(repos: readonly RepoItem[] | null): RepoItem | null {
  if (!repos?.length) return null
  return (
    repos.find((r) => r.status === 'ok') ??
    repos.find((r) => r.status === 'uncommitted') ??
    repos.find((r) => r.status === 'not_installed') ??
    repos[0] ??
    null
  )
}

export function gettingStartedSteps(input: GettingStartedInput): Step[] {
  const { check, library, repos } = input
  const repo = focusRepo(repos)
  const harnesses = detectedHarnesses(check)
  const installed = !!repos?.some((r) => r.status === 'ok')
  const factoryHref = repo ? repoHref(repo.id, 'factory') : REPOS_ADD_HREF
  return [
    {
      id: 'machine',
      title: 'Tento počítač',
      done: !!check?.ok,
      hint: check ? (check.ok ? 'Kontrola počítače bez chyb.' : 'Kontrola počítače hlásí chyby.') : 'Kontrola počítače ještě neproběhla.',
      href: '#/setup',
      action: 'Zkontrolovat počítač',
    },
    {
      id: 'library',
      title: 'Knihovna',
      done: library?.exists === true,
      hint: library?.exists ? 'Knihovna agentů a workflow je připravená.' : 'Založ knihovnu ze semínka nebo naklonuj týmovou.',
      href: library?.exists ? '#/library' : '#/setup',
      action: 'Připravit knihovnu',
    },
    {
      id: 'harnesses',
      title: 'Harnessy',
      done: harnesses.length > 0,
      hint: harnesses.length ? `Přihlášené: ${harnesses.join(', ')}.` : 'Nainstaluj a přihlas aspoň jeden harness (claude, codex nebo pi).',
      href: '#/setup',
      action: 'Zkontrolovat harnessy',
    },
    {
      id: 'repo',
      title: 'Repozitář',
      done: !!repos?.length,
      hint: repos?.length ? `V dashboardu: ${repos.map((r) => r.name).join(', ')}.` : 'Přidej repozitář, ve kterém bude factory pracovat.',
      href: REPOS_ADD_HREF,
      action: 'Přidat repozitář',
    },
    {
      id: 'factory',
      title: 'Factory v repu',
      done: installed,
      hint: installed
        ? 'Factory je nainstalovaná a commitnutá.'
        : repo?.status === 'uncommitted'
          ? `Konfigurace factory v ${repo.name} není commitnutá.`
          : 'Nainstaluj factory v záložce Factory repa.',
      href: factoryHref,
      action: repo?.status === 'uncommitted' ? 'Commitnout konfiguraci' : 'Nainstalovat factory',
    },
    {
      id: 'roster',
      title: 'Harnessy a modely repa',
      done: installed && (input.rosterAgents ?? 0) > 0,
      hint: 'Zkontroluj harness, model a přemýšlení agentů v záložce Factory.',
      href: factoryHref,
      action: 'Zkontrolovat agenty',
    },
    {
      id: 'project',
      title: 'První projekt',
      done: (input.projects ?? 0) > 0,
      hint: 'Založ v backlogu projekt, pak kroky a tasky.',
      href: repo ? repoHref(repo.id, 'backlog', NEW_CONTAINER) : REPOS_ADD_HREF,
      action: 'Založit projekt',
    },
  ]
}

/** The first step not done yet; null when everything is ready. */
export function nextStep(steps: readonly Step[]): Step | null {
  return steps.find((s) => !s.done) ?? null
}

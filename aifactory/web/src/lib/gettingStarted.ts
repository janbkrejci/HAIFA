import { t } from './i18n'
// The steps of the first visit: from this machine to the first project of a backlog. The
// unfinished ones are readiness issues (topbar chip, #/problems on the overview). Pure: the
// readiness loads the inputs, this decides the states.
import type { MachineCheck, RepoItem } from './api'
import type { LibraryStatus } from './library'
import { detectedHarnesses } from './roster'
import { LIBRARY_HREF, NEW_CONTAINER, REPOS_ADD_HREF, SETUP_HREF, repoHref } from './router'

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
      get title() { return t('dashboard.machine') },
      done: !!check?.ok,
      get hint() { return check ? (check.ok ? t('dashboard.machineOk') : t('dashboard.machineErrors')) : t('dashboard.machineUnchecked') },
      href: SETUP_HREF,
      get action() { return t('dashboard.checkMachine') },
    },
    {
      id: 'library',
      get title() { return t('dashboard.library') },
      done: library?.exists === true,
      get hint() { return library?.exists ? t('dashboard.libraryReady') : t('dashboard.libraryPrepareHint') },
      href: LIBRARY_HREF,
      get action() { return t('dashboard.prepareLibrary') },
    },
    {
      id: 'harnesses',
      get title() { return t('dashboard.harnesses') },
      done: harnesses.length > 0,
      get hint() { return harnesses.length ? t('dashboard.signedIn', { names: harnesses.join(', ') }) : t('dashboard.installHarness') },
      href: SETUP_HREF,
      get action() { return t('dashboard.checkHarnesses') },
    },
    {
      id: 'repo',
      get title() { return t('dashboard.repository') },
      done: !!repos?.length,
      get hint() { return repos?.length ? t('dashboard.registered', { names: repos.map((r) => r.name).join(', ') }) : t('dashboard.addRepoHint') },
      href: REPOS_ADD_HREF,
      get action() { return t('dashboard.addRepo') },
    },
    {
      id: 'factory',
      get title() { return t('dashboard.factoryRepo') },
      done: installed,
      get hint() { return installed
        ? t('dashboard.factoryInstalled')
        : repo?.status === 'uncommitted'
          ? t('dashboard.repoConfigDirty', { name: repo.name })
          : t('dashboard.installFactoryHint') },
      href: factoryHref,
      get action() { return repo?.status === 'uncommitted' ? t('dashboard.commitConfig') : t('dashboard.installFactory') },
    },
    {
      id: 'roster',
      get title() { return t('dashboard.repoAgents') },
      done: installed && (input.rosterAgents ?? 0) > 0,
      get hint() { return t('dashboard.checkAgentsHint') },
      href: factoryHref,
      get action() { return t('dashboard.checkAgents') },
    },
    {
      id: 'project',
      get title() { return t('dashboard.firstProject') },
      done: (input.projects ?? 0) > 0,
      get hint() { return t('dashboard.createProjectHint') },
      href: repo ? repoHref(repo.id, 'backlog', NEW_CONTAINER) : REPOS_ADD_HREF,
      get action() { return t('dashboard.createProject') },
    },
  ]
}

/** The first step not done yet; null when everything is ready. */
export function nextStep(steps: readonly Step[]): Step | null {
  return steps.find((s) => !s.done) ?? null
}

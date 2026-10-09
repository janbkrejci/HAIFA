// Texts and helpers shared by the repo pages (overview, list, add, Factory tab) of the
// multi-repo dashboard.
import { ref } from 'vue'
import {
  ApiError,
  removeRepo,
  type FactoryState,
  type Onboarding,
  type OnboardingSource,
  type RepoStatus,
} from './api'
import { fmtTime, errorText, shortSha } from './format'
import { useConfirm, type ConfirmOptions } from './confirm'
import { OVERVIEW_HREF, currentRepoId } from './router'

/** How a repository gets into the dashboard: the Add page, or the terminal. */
export const ADD_REPO_HINT =
  'Repozitář přidáš tlačítkem Přidat repozitář. Z terminálu ho zaregistruje a otevře příkaz factory obs --repo <cesta>.'

export const REPO_STATUS_TEXT: Record<RepoStatus, string> = {
  ok: 'ok',
  uncommitted: 'neuložená konfigurace',
  not_installed: 'nenainstalováno',
  missing: 'chybí',
  not_git: 'není git',
}

export function repoStatusText(status: string): string {
  return REPO_STATUS_TEXT[status as RepoStatus] ?? status
}

export const FACTORY_STATE_TEXT: Record<FactoryState, string> = {
  none: 'Bez factory',
  working_tree: 'konfigurace jen v pracovním stromu (necommitnutá)',
  sssf: 'sssf',
  pre_library: 'HAIFA před knihovnou',
  onboarded: 'Onboardováno',
}

export function factoryStateText(state: string | null | undefined, prId?: string): string {
  if (!state) return '—'
  if (state === 'onboarded_in_remote') return 'Onboardováno na remote'
  if (state === 'onboarding_pending') return `Čeká v PR${prId ? ' #' + prId : ''}`
  return FACTORY_STATE_TEXT[state as FactoryState] ?? state
}

export const ONBOARDING_SOURCE_TEXT: Record<OnboardingSource, string> = {
  init: 'factory init',
  sssf: 'převod ze sssf',
  pre_library: 'factory z doby před knihovnou',
}

export function onboardingSourceText(source: string): string {
  return ONBOARDING_SOURCE_TEXT[source as OnboardingSource] ?? source
}

/** Who onboarded the repo, when and from what (`Onboardoval … z …`). */
export function onboardingText(o: Onboarding): string {
  const parts = [`Onboardoval ${o.by ?? 'neznámo'} ${fmtTime(o.at)} z ${onboardingSourceText(o.source)}`]
  if (o.source_commit) parts.push(`commit ${shortSha(o.source_commit, 8)}`)
  if (o.factory) parts.push(`factory ${o.factory}`)
  return parts.join(', ')
}

/** The question before a repo leaves the dashboard; nothing in its folder changes. */
export function removeConfirm(repo: { name: string; path: string }): ConfirmOptions {
  return {
    title: `Odebrat ${repo.name} z dashboardu?`,
    message: `Ve složce ${repo.path} se nic nezmění: .factory/, backlog, trace DB, worktree a větve zůstanou. Běžící běhy doběhnou.`,
    confirmLabel: 'Odebrat',
    tone: 'danger',
  }
}

/**
 * Removing a repo from the dashboard: asks in the shared ConfirmDialog (bind `dialog`,
 * `confirm`, `cancel`), sends DELETE and calls `onRemoved`. A repo removed by someone else
 * (`unknown_repo`) counts as removed. Removing the open repo goes to the overview.
 */
export function useRemoveRepo(onRemoved: (id: string) => void) {
  const { dialog, ask, confirm, cancel } = useConfirm()
  const removing = ref<string | null>(null)
  const error = ref<string | null>(null)

  async function remove(repo: { id: string; name: string; path: string }): Promise<boolean> {
    error.value = null
    if (!(await ask(removeConfirm(repo)))) return false
    removing.value = repo.id
    try {
      await removeRepo(repo.id)
    } catch (err) {
      if (!(err instanceof ApiError && err.code === 'unknown_repo')) {
        error.value = errorText(err)
        return false
      }
    } finally {
      removing.value = null
    }
    if (currentRepoId() === repo.id) window.location.hash = OVERVIEW_HREF
    onRemoved(repo.id)
    return true
  }

  return { dialog, confirm, cancel, remove, removing, error }
}

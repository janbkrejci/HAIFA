// Texts and helpers shared by the repo pages (overview, list, add, Factory tab) of the
// multi-repo dashboard.
import { ref } from 'vue'
import {
  ApiError,
  fetchRepoRemoval,
  removeRepo,
  type FactoryState,
  type OwnItem,
  type RepoRemoval,
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

/**
 * The question before a repo is removed: with a removal plan it says what the commit on base
 * deletes and what stays; without one (the plan could not be read) only the registry entry goes.
 */
export function removeConfirm(
  repo: { name: string; path: string },
  plan: RepoRemoval | null,
  planError: string | null = null,
): ConfirmOptions {
  const message = plan
    ? `Smaže z repa .factory/ a řádky factory v .gitignore, commitne to do ${plan.base} a pushne (má-li repo remote). ` +
      'Smaže i lokální data běhů (trace DB, worktree). Backlog, specifikace a dokumentace v repu zůstanou.'
    : `Plán odebrání se nepodařilo načíst: ${planError ?? 'neznámá chyba'}. ` +
      `Repo se odebere jen z dashboardu, ve složce ${repo.path} se nic nezmění.`
  return {
    title: `Odebrat repozitář ${repo.name}?`,
    message,
    confirmLabel: 'Odebrat',
    tone: 'danger',
    confirmDisabled: (plan?.blockers.length ?? 0) > 0,
  }
}

/** One own item of the repo and whether it goes to the library before the removal. */
export interface ExportChoice {
  item: OwnItem
  export: boolean
}

/**
 * Removing a repo: reads its removal plan (GET .../removal), asks in the shared ConfirmDialog
 * (render `RemoveRepoDialog` with this object), sends DELETE with the chosen exports and
 * calls `onRemoved`. A repo removed by someone else (`unknown_repo`) counts as removed.
 * Removing the open repo goes to the overview.
 */
export function useRemoveRepo(onRemoved: (id: string) => void) {
  const { dialog, ask, confirm, cancel } = useConfirm()
  const removing = ref<string | null>(null)
  const error = ref<string | null>(null)
  const plan = ref<RepoRemoval | null>(null)
  const choices = ref<ExportChoice[]>([])

  function gone(id: string): true {
    if (currentRepoId() === id) window.location.hash = OVERVIEW_HREF
    onRemoved(id)
    return true
  }

  async function remove(repo: { id: string; name: string; path: string }): Promise<boolean> {
    error.value = null
    plan.value = null
    choices.value = []
    let planError: string | null = null
    removing.value = repo.id
    try {
      plan.value = await fetchRepoRemoval(repo.id)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'unknown_repo') {
        removing.value = null
        return gone(repo.id)
      }
      planError = errorText(err)
    } finally {
      removing.value = null
    }
    const current = plan.value
    choices.value = (current?.own_items ?? []).map((item) => ({ item, export: true }))
    if (!(await ask(removeConfirm(repo, current, planError)))) return false
    removing.value = repo.id
    try {
      const exported = choices.value.filter((c) => c.export).map((c) => ({ type: c.item.type, name: c.item.name }))
      await removeRepo(repo.id, current ? { export: exported } : { uninstall: false })
    } catch (err) {
      if (!(err instanceof ApiError && err.code === 'unknown_repo')) {
        error.value = errorText(err)
        return false
      }
    } finally {
      removing.value = null
    }
    return gone(repo.id)
  }

  return { dialog, confirm, cancel, remove, removing, error, plan, choices }
}

export type RepoRemover = ReturnType<typeof useRemoveRepo>

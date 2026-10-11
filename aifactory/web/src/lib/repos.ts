// Texts and helpers shared by the repo pages (overview, list, add, Factory tab) of the
// multi-repo dashboard.
import { ref } from 'vue'
import {
  ApiError,
  fetchRepoRemoval,
  removeRepo,
  type FactoryState,
  type RepoRemoval,
  type RepoStatus,
} from './api'
import { errorText } from './format'
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
  uncommitted: 'konfigurace jen v pracovním stromu (necommitnutá)',
  unsupported: 'Nepodporováno: HAIFA tuto konfiguraci nepřevezme',
  installed: 'Nainstalováno',
}

export function factoryStateText(state: string | null | undefined): string {
  if (!state) return '—'
  return FACTORY_STATE_TEXT[state as FactoryState] ?? state
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

/**
 * Removing a repo: reads its removal plan (GET .../removal), asks in the shared ConfirmDialog
 * (render `RemoveRepoDialog` with this object), sends DELETE and
 * calls `onRemoved`. A repo removed by someone else (`unknown_repo`) counts as removed.
 * Removing the open repo goes to the overview.
 */
export function useRemoveRepo(onRemoved: (id: string) => void) {
  const { dialog, ask, confirm, cancel } = useConfirm()
  const removing = ref<string | null>(null)
  const error = ref<string | null>(null)
  const plan = ref<RepoRemoval | null>(null)

  function gone(id: string): true {
    if (currentRepoId() === id) window.location.hash = OVERVIEW_HREF
    onRemoved(id)
    return true
  }

  async function remove(repo: { id: string; name: string; path: string }): Promise<boolean> {
    error.value = null
    plan.value = null
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
    if (!(await ask(removeConfirm(repo, current, planError)))) return false
    removing.value = repo.id
    try {
      await removeRepo(repo.id, current ? {} : { uninstall: false })
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

  return { dialog, confirm, cancel, remove, removing, error, plan }
}

export type RepoRemover = ReturnType<typeof useRemoveRepo>

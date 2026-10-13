// Texts and helpers shared by the repo pages (overview, list, add, Factory tab) of the
// multi-repo dashboard.
import { ref } from 'vue'
import {
  ApiError,
  removeRepo,
  type FactoryState,
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
 * The question before a repo is removed: it only leaves the dashboard; the folder, its .factory/
 * and its history stay as they are.
 */
export function removeConfirm(repo: { name: string; path: string }): ConfirmOptions {
  return {
    title: `Odebrat repozitář ${repo.name}?`,
    message:
      `Repo se odpojí jen z dashboardu, ve složce ${repo.path} se nic nezmění: .factory/, backlog, specifikace ` +
      'i dokumentace v repu zůstanou. Kdykoli ho můžeš znovu přidat.',
    confirmLabel: 'Odebrat',
    tone: 'danger',
  }
}

/**
 * Removing a repo from the dashboard: asks in the shared ConfirmDialog (render `RemoveRepoDialog`
 * with this object), sends DELETE and calls `onRemoved`. A repo removed by someone else
 * (`unknown_repo`) counts as removed. Removing the open repo goes to the overview.
 */
export function useRemoveRepo(onRemoved: (id: string) => void) {
  const { dialog, ask, confirm, cancel } = useConfirm()
  const removing = ref<string | null>(null)
  const error = ref<string | null>(null)

  function gone(id: string): true {
    if (currentRepoId() === id) window.location.hash = OVERVIEW_HREF
    onRemoved(id)
    return true
  }

  async function remove(repo: { id: string; name: string; path: string }): Promise<boolean> {
    error.value = null
    if (!(await ask(removeConfirm(repo)))) return false
    removing.value = repo.id
    try {
      await removeRepo(repo.id, { uninstall: false })
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

  return { dialog, confirm, cancel, remove, removing, error }
}

export type RepoRemover = ReturnType<typeof useRemoveRepo>

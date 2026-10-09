// The config status (D4) of each repo for the banner of the repo screen and the Settings screen.
// Kept per repo id: an answer is recorded under the repo it was asked for, so a late answer
// for one repo never shows on another.
import { computed, reactive } from 'vue'
import { ApiError } from './api'
import { currentRepoId, useRepoId } from './router'
import { fetchConfigStatus, type ConfigStatus } from './settings'

interface Entry {
  status: ConfigStatus | null
  error: string | null
}

const statuses = reactive(new Map<string, Entry>())

async function refreshFor(repo: string | null): Promise<void> {
  // the request goes to the repo in the URL: never record it under another one
  if (repo === null || repo !== currentRepoId()) return
  let entry: Entry
  try {
    entry = { status: await fetchConfigStatus(), error: null }
  } catch (err) {
    entry = { status: null, error: err instanceof ApiError ? err.message : null }
  }
  statuses.set(repo, entry)
}

/** The status of `repoId` (default: the repo in the URL when called). */
export function useConfigStatus(repoId?: string) {
  const route = useRepoId()
  const entry = () => {
    const id = repoId ?? route.value
    return id === null ? undefined : statuses.get(id)
  }
  return {
    status: computed(() => entry()?.status ?? null),
    error: computed(() => entry()?.error ?? null),
    refresh: () => refreshFor(repoId ?? currentRepoId()),
  }
}

/** Test helper: forget every repo's status. */
export function resetConfigStatusForTests(): void {
  statuses.clear()
}

// One shared status of the uncommitted backlog (writes stay in the working tree, runs read
// base) for the banner of the repo screen (RepoScreen.vue): refreshed on backlog file events,
// committed at once. A repo switch resets it, and answers for the previous repo are dropped.
import { ref } from 'vue'
import { commitBacklog, fetchBacklogStatus, type BacklogCommitResult, type BacklogStatus } from './backlog'
import { errorText } from './format'

const status = ref<BacklogStatus | null>(null)
const committing = ref(false)
const commitError = ref<string | null>(null)
/** The pull request the last commit opened (`base_changes: pr`), until base has the change. */
const pendingPr = ref<{ url: string; branch: string } | null>(null)
const commitWarnings = ref<string[]>([])
let generation = 0

async function refresh(): Promise<void> {
  const mine = generation
  try {
    const next = await fetchBacklogStatus()
    if (mine === generation) {
      status.value = next
      if (next?.clean) {
        pendingPr.value = null
        commitWarnings.value = []
      }
    }
  } catch {
    if (mine === generation) status.value = null // unknown: no banner
  }
}

/** Commit every backlog change to base (`factory backlog commit`), then read the status again. */
function acceptCommit(result: BacklogCommitResult): void {
  pendingPr.value = result.pr && !result.merged ? result.pr : null
  commitWarnings.value = result.warnings ?? []
}

async function commit(): Promise<void> {
  committing.value = true
  commitError.value = null
  try {
    const result = await commitBacklog()
    acceptCommit(result)
  } catch (err) {
    commitError.value = errorText(err)
  } finally {
    committing.value = false
  }
  await refresh()
}

export function useBacklogStatus() {
  return { status, committing, commitError, commitWarnings, pendingPr, refresh, commit, acceptCommit }
}

/** Forget the status and the last commit error (a repo screen starts clean). */
export function resetBacklogStatus(): void {
  generation += 1
  status.value = null
  committing.value = false
  commitError.value = null
  pendingPr.value = null
  commitWarnings.value = []
}

/** Test helper: same as resetBacklogStatus. */
export const resetBacklogStatusForTests = resetBacklogStatus

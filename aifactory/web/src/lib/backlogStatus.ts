// One shared status of the uncommitted backlog (writes stay in the working tree, runs read
// base) for the banner of the repo screen (RepoScreen.vue): refreshed on backlog file events,
// committed at once. A repo switch resets it, and answers for the previous repo are dropped.
import { ref } from 'vue'
import { commitBacklog, fetchBacklogStatus, type BacklogStatus } from './backlog'
import { errorText } from './format'

const status = ref<BacklogStatus | null>(null)
const committing = ref(false)
const commitError = ref<string | null>(null)
let generation = 0

async function refresh(): Promise<void> {
  const mine = generation
  try {
    const next = await fetchBacklogStatus()
    if (mine === generation) status.value = next
  } catch {
    if (mine === generation) status.value = null // unknown: no banner
  }
}

/** Commit every backlog change to base (`factory backlog commit`), then read the status again. */
async function commit(): Promise<void> {
  committing.value = true
  commitError.value = null
  try {
    await commitBacklog()
  } catch (err) {
    commitError.value = errorText(err)
  } finally {
    committing.value = false
  }
  await refresh()
}

export function useBacklogStatus() {
  return { status, committing, commitError, refresh, commit }
}

/** Forget the status and the last commit error (a repo screen starts clean). */
export function resetBacklogStatus(): void {
  generation += 1
  status.value = null
  committing.value = false
  commitError.value = null
}

/** Test helper: same as resetBacklogStatus. */
export const resetBacklogStatusForTests = resetBacklogStatus

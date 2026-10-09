<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import BackLink from '@/components/ui/BackLink.vue'
import ReviewDetail from '@/components/review/ReviewDetail.vue'
import ReviewList from '@/components/review/ReviewList.vue'
import { ApiError, isDbBusy, isDbBusyText } from '@/lib/api'
import { touchesTask, useLive, type LiveFilesEvent, type LiveTraceEvent } from '@/lib/live'
import { here, reviewHref, runHref, useRouteParams } from '@/lib/router'
import { errorText, shortSha } from '@/lib/format'
import { newRun } from '@/lib/backlog'
import {
  approvePr,
  fetchReview,
  fetchReviews,
  loadShowDone,
  resolvePr,
  returnPr,
  saveShowDone,
  type ActionStarted,
  type ReviewAction,
  type ReviewDetail as ReviewDetailData,
  type ReviewList as ReviewListData,
} from '@/lib/review'

const params = useRouteParams()
const taskId = computed(() => params.value[0] ?? null)

const loading = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
/** The PR this screen just merged, and the next PR waiting for approval (null: none). */
const merged = ref<{ taskId: string; sha: string; note: string; next: string | null } | null>(null)
/** Bumped after a successful return: ReviewActions clears the note. */
const returned = ref(0)
const started = ref<ActionStarted | null>(null)
/** The action whose button spins: until the server answers, or until a `pending` run shows up. */
const pendingAction = ref<ReviewAction | null>(null)
/** Return/resolve answered `pending`: waiting for the run in live updates. */
const waiting = ref(false)
/** Runs of the PR before the action, to recognise the run it launched. */
let knownRuns = new Set<string>()
/** An action that failed on a busy trace DB: "Zkusit znovu" repeats it. */
const retryAction = ref<(() => void) | null>(null)
/** The list arrived at least once: until then it shows no empty state. */
const listReady = ref(false)

/** "Zobrazit hotové": the list also has merged and closed PRs; remembered by the browser. */
const showDone = ref(loadShowDone())

const list = ref<ReviewListData>(emptyList())
const detail = ref<ReviewDetailData | null>(null)
/** The task id `detail` belongs to: a PR of another task is never shown. */
const detailFor = ref<string | null>(null)
/** The PR of the open task, or null while it loads after a switch. */
const shownDetail = computed(() =>
  detail.value && detailFor.value === taskId.value ? detail.value : null,
)
/** Number of the latest screen load: an answer of an older load is dropped. */
let loadSeq = 0

function setDetail(id: string, data: ReviewDetailData | null) {
  detail.value = data
  detailFor.value = data ? id : null
  if (data) claimPending(data)
}

function emptyList(): ReviewListData {
  return {
    prs: [],
    done: [],
    provider: '',
    approve_review_sent: false,
    approve_note: '',
  }
}

function normalise(data: Partial<ReviewListData> | null | undefined): ReviewListData {
  return {
    ...emptyList(),
    ...(data ?? {}),
    prs: Array.isArray(data?.prs) ? data.prs : [],
    done: Array.isArray(data?.done) ? data.done : [],
  }
}

function message(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'conflict') return `${e.message} – použij Vyřešit konflikt s base`
    return e.message
  }
  return errorText(e)
}

/** The next open PR to approve after `id`: one waiting for review first, else any other. */
async function nextPr(id: string): Promise<string | null> {
  try {
    const prs = normalise(await fetchReviews()).prs.filter((p) => p.task_id !== id)
    return (prs.find((p) => p.awaiting_review) ?? prs[0])?.task_id ?? null
  } catch {
    return null // the box keeps "Zpět na seznam"
  }
}

async function loadList() {
  const seq = ++loadSeq
  loading.value = true
  error.value = null
  try {
    const data = normalise(await fetchReviews({ done: showDone.value }))
    if (seq !== loadSeq) return
    list.value = data
    listReady.value = true
  } catch (e) {
    if (seq === loadSeq) error.value = `PR se nepodařilo načíst: ${message(e)}`
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function loadDetail(id: string) {
  const seq = ++loadSeq
  loading.value = true
  error.value = null
  // another PR: drop the previous one at once, a reload of the same PR keeps it shown
  if (detailFor.value !== id) setDetail(id, null)
  try {
    const data = await fetchReview(id)
    if (seq !== loadSeq || taskId.value !== id) return
    setDetail(id, data?.pr ? data : null)
  } catch (e) {
    if (seq !== loadSeq || taskId.value !== id) return
    setDetail(id, null)
    if (e instanceof ApiError && e.code === 'no_pr') error.value = `Task ${id} nemá PR: ${e.message}`
    else error.value = `PR tasku ${id} se nepodařilo načíst: ${message(e)}`
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function reload() {
  if (taskId.value) void loadDetail(taskId.value)
  else void loadList()
}

/** "Zkusit znovu" after a busy trace DB: repeat the failed action, else reload. */
function onRetry() {
  const again = retryAction.value
  retryAction.value = null
  if (again) again()
  else reload()
}

/** Refresh the list quietly (no spinner). */
async function refreshList() {
  try {
    const data = normalise(await fetchReviews({ done: showDone.value }))
    if (!taskId.value) {
      list.value = data
      listReady.value = true
    }
  } catch (e) {
    error.value = `PR se nepodařilo načíst: ${message(e)}`
  }
}

/** Refresh the open PR quietly, keeping the page when it fails. */
async function refreshDetail(id: string) {
  try {
    const data = await fetchReview(id)
    if (taskId.value === id && data?.pr) setDetail(id, data)
  } catch (e) {
    error.value = `PR tasku ${id} se nepodařilo obnovit: ${message(e)}`
  }
}

/** A `pending` run showed up in the PR's runs: show its link and stop the spinner. */
function claimPending(data: ReviewDetailData) {
  const current = started.value
  if (!waiting.value || !current || data.task_id !== taskId.value) return
  const found = newRun(data.runs, knownRuns)
  if (!found) return
  started.value = {
    ...current,
    run: { run_id: found.run_id, workflow: found.workflow, branch: data.pr.branch },
    pending: false,
  }
  waiting.value = false
  pendingAction.value = null
}

function idle(): boolean {
  return !busy.value && !loading.value
}

function onFiles(event: LiveFilesEvent) {
  if (!idle()) return
  const id = taskId.value
  if (id) {
    if (event.truncated || touchesTask(event.paths, id)) void refreshDetail(id)
  } else if (event.areas.includes('backlog')) void refreshList()
}

function onTrace(event: LiveTraceEvent) {
  if (!idle()) return
  const id = taskId.value
  if (id) {
    if (event.task_ids.includes(id)) void refreshDetail(id)
  } else if (event.runs_changed) void refreshList()
}

useLive({ files: onFiles, trace: onTrace, resync: () => idle() && reload() })

async function act(key: ReviewAction, run: () => Promise<void>, failure: string) {
  busy.value = true
  pendingAction.value = key
  waiting.value = false
  knownRuns = new Set((detail.value?.runs ?? []).map((r) => r.run_id))
  error.value = null
  merged.value = null
  started.value = null
  retryAction.value = null
  let failed: string | null = null
  try {
    await run()
    // `pending`: the run is still starting; the spinner stays until live updates bring it
    // `started` is set inside run(): read it without the narrowing from `= null` above
    const answer = started.value as ActionStarted | null
    waiting.value = answer?.pending === true && !answer.run
  } catch (e) {
    failed = `${failure}: ${message(e)}`
    if (isDbBusy(e)) retryAction.value = () => void act(key, run, failure)
  } finally {
    busy.value = false
    if (!waiting.value) pendingAction.value = null
  }
  if (taskId.value) await loadDetail(taskId.value)
  if (failed) error.value = error.value ? `${failed} · ${error.value}` : failed
}

function onApprove() {
  const id = taskId.value
  if (!id) return
  void act('approve', async () => {
    const result = await approvePr(id)
    const next = await nextPr(id)
    merged.value = { taskId: id, sha: shortSha(result.merge_sha), note: result.approve_note ?? '', next }
  }, 'Schválení selhalo')
}

function onReturn(note: string) {
  const id = taskId.value
  if (!id) return
  void act('return', async () => {
    started.value = await returnPr(id, note)
    returned.value += 1
  }, 'Vrácení selhalo')
}

function onResolve() {
  const id = taskId.value
  if (!id) return
  void act('resolve', async () => {
    started.value = await resolvePr(id)
  }, 'Vyřešení konfliktu selhalo')
}

watch(showDone, (value) => {
  saveShowDone(value)
  if (!taskId.value) void loadList()
})

watch(
  taskId,
  (id, previous) => {
    if (id !== previous || id === null) {
      merged.value = null
      started.value = null
      waiting.value = false
      pendingAction.value = null
      if (id !== detailFor.value) setDetail(id ?? '', null)
      reload()
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="review-view">
    <div class="view-head">
      <h1>Review</h1>
      <BackLink v-if="taskId" :href="here('review')" label="všechny PR" />
      <label v-if="!taskId" class="show-done">
        <input v-model="showDone" type="checkbox" data-test="show-done" /> Zobrazit hotové
      </label>
      <button type="button" class="refresh" data-test="refresh" :disabled="loading" @click="reload">
        <RefreshCw :size="16" :class="{ spin: loading }" /> Obnovit
      </button>
    </div>
    <p v-if="error" class="error-bar" data-test="error">
      {{ error }}
      <button v-if="isDbBusyText(error)" type="button" class="retry" data-test="retry" @click="onRetry">
        Zkusit znovu
      </button>
    </p>
    <div v-if="merged && merged.taskId === taskId" class="notice merged" data-test="merged">
      <p data-test="notice">
        <strong>Sloučeno</strong><template v-if="merged.sha"> (merge {{ merged.sha }})</template>.
        {{ merged.note }}
      </p>
      <p class="merged-hint">
        Pokud má krok zapnuté auto continue, další task se spustí automaticky; pořadí určuje kanban.
      </p>
      <div class="merged-actions">
        <a v-if="merged.next" class="btn" :href="reviewHref(merged.next)" data-test="next-pr">
          Další PR ke schválení
        </a>
        <a class="btn" :href="here('review')" data-test="back-to-list">Zpět na seznam</a>
      </div>
    </div>
    <p v-if="started" class="notice" data-test="started">
      <template v-if="started.run">
        Spuštěn běh
        <a :href="runHref(started.run.run_id)">{{ started.run.run_id }}</a>
        ({{ started.action === 'return' ? 'vrácení' : 'resolve' }})
      </template>
      <template v-else>Běh se spouští…</template>
    </p>

    <template v-if="taskId">
      <ReviewDetail
        v-if="shownDetail"
        :detail="shownDetail"
        :busy="busy || waiting"
        :pending="pendingAction"
        :returned="returned"
        @approve="onApprove"
        @return="onReturn"
        @resolve="onResolve"
      />
      <p v-else-if="loading" class="faint" data-test="detail-loading">
        <span class="mono" data-test="loading-id">{{ taskId }}</span> · Načítám…
      </p>
    </template>
    <ReviewList v-else :list="list" :ready="listReady" :loading="loading" :show-done="showDone" />
  </section>
</template>

<style scoped>
.review-view {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}

.view-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

.show-done {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  color: var(--dim);
  cursor: pointer;
}

.show-done + .refresh {
  margin-left: 0;
}

.refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.notice {
  padding: 8px 12px;
  border: 1px solid rgba(74, 222, 128, 0.45);
  border-radius: 8px;
  background: rgba(74, 222, 128, 0.08);
  color: var(--green);
}

.merged p {
  margin: 0 0 6px;
}

.merged-hint {
  color: var(--dim);
}

.merged-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.merged-actions .btn {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  text-decoration: none;
}
</style>

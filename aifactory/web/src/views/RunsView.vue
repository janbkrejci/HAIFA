<script setup lang="ts">
import { runError } from '@/lib/runMessages'
import { t } from '@/lib/i18n'
import { computed, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import BackLink from '@/components/ui/BackLink.vue'
import CostTotals from '@/components/runs/CostTotals.vue'
import RunDetail from '@/components/runs/RunDetail.vue'
import RunsList from '@/components/runs/RunsList.vue'
import ChainPanel from '@/components/runs/ChainPanel.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import { isDbBusy } from '@/lib/api'
import { chainsOf, dismissChain, fetchChains, type Chain } from '@/lib/chains'
import { useConfirm } from '@/lib/confirm'
import { useLive, type LiveTraceEvent } from '@/lib/live'
import { here, useRouteParams } from '@/lib/router'
import {
  applyTail,
  archiveFinishedRuns,
  archiveRun,
  cursorsOf,
  deleteArchivedRuns,
  deleteRun,
  fetchAllEvents,
  fetchRun,
  fetchRunTail,
  fetchRunTotals,
  fetchRuns,
  pauseRun,
  publishRun,
  resumeRun,
  stopRun,
  unarchiveRun,
  type RunCursors,
  type RunDetail as RunDetailData,
  type RunTotals,
  type RunSummary,
  type TraceEvent,
} from '@/lib/runs'

const params = useRouteParams()
const runId = computed(() => params.value[0] ?? null)
const phaseId = computed(() => params.value[1] ?? null)

const loading = ref(false)
/** The list arrived at least once: until then it shows no empty state. */
const listReady = ref(false)
const retryableError = ref(false)
const errorSource = ref<(() => string) | null>(null)
const error = computed(() => errorSource.value?.() ?? null)

const runs = ref<RunSummary[]>([])
const runTasks = ref<string[]>([])
const stateFilter = ref('')
const taskFilter = ref('')
const stateOptions = computed(() => [
  { value: '', label: t('runs.vsechny_stavy') },
  { value: 'running', label: t('runs.bezi') },
  { value: 'paused', label: t('runs.pozastavene') },
  { value: 'succeeded', label: t('runs.uspesne') },
  { value: 'failed', label: t('runs.stateFailed') },
  { value: 'aborted', label: t('runs.prerusene') },
  { value: 'stopped', label: t('runs.zastavene') },
])
const taskOptions = computed(() => [
  { value: '', label: t('runs.vsechny_tasky') },
  ...runTasks.value.map((task) => ({ value: task, label: task })),
])
const offset = ref(0)
const totalRuns = ref(0)
const pageSize = 100
let listSeq = 0
let listLoadingSeq = 0

async function readList(): Promise<boolean> {
  const seq = ++listSeq
  const data = await fetchRuns(archived.value, {
    ...(offset.value ? { offset: offset.value } : {}),
    ...(stateFilter.value ? { state: stateFilter.value } : {}),
    ...(taskFilter.value ? { task: taskFilter.value } : {}),
  }).catch((error: unknown) => {
    if (seq === listSeq) throw error
    return null
  })
  if (seq !== listSeq) return false
  if (!data) return false
  if (offset.value > 0 && data.total !== undefined && offset.value >= data.total) {
    offset.value = Math.max(0, Math.floor((data.total - 1) / pageSize) * pageSize)
    return readList()
  }
  runs.value = Array.isArray(data?.runs) ? data.runs : []
  runTasks.value = data.tasks ?? [...new Set(runs.value.map((run) => run.task_id))]
  totalRuns.value = data.total ?? runs.value.length
  listReady.value = true
  return true
}

function changePage(delta: number) {
  offset.value = Math.max(0, offset.value + delta * pageSize)
  void loadList()
}

function filterList() {
  offset.value = 0
  void loadList()
}
/** Auto-continue chains; a failure to load them leaves the list of runs alone. */
const chains = ref<Chain[]>([])
/** The chain being hidden. */
const dismissing = ref<string | null>(null)
/** Cost totals: folded by default, loaded when the section opens (and refreshed while open). */
const totals = ref<RunTotals | null>(null)
const totalsOpen = ref(false)
const totalsLoading = ref(false)
const totalsErrorSource = ref<(() => string) | null>(null)
const totalsError = computed(() => totalsErrorSource.value?.() ?? null)
/** The archived view: only archived runs; otherwise only the active ones. Totals keep every run. */
const archived = ref(false)
/** An archive or delete request is on its way. */
const archiving = ref(false)
const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

const detail = ref<RunDetailData | null>(null)
const events = ref<TraceEvent[]>([])
const stopping = ref(false)
const pauseBusy = ref(false)
const publishing = ref(false)
let cursors: RunCursors | null = null
let tailing = false
let tailAgain = false

async function loadTotals() {
  totalsLoading.value = true
  totalsErrorSource.value = null
  try {
    totals.value = await fetchRunTotals()
  } catch (e) {
    retryableError.value = isDbBusy(e)
    totalsErrorSource.value = () => t('runs.naklady_se_nepodarilo_nacist_p0', { p0: runError(e) })
  } finally {
    totalsLoading.value = false
  }
}

function toggleTotals() {
  totalsOpen.value = !totalsOpen.value
  if (totalsOpen.value) void loadTotals()
}

async function loadChains() {
  try {
    chains.value = chainsOf(await fetchChains())
  } catch {
    // the panel keeps what it showed; the runs list reports its own errors
  }
}

async function onDismissChain(chainId: string) {
  dismissing.value = chainId
  try {
    await dismissChain(chainId)
    chains.value = chains.value.filter((c) => c.chain_id !== chainId)
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => t('runs.retez_se_nepodarilo_skryt_p0', { p0: runError(e) })
  } finally {
    dismissing.value = null
  }
}

async function loadList() {
  loading.value = true
  errorSource.value = null
  void loadChains()
  const seq = ++listLoadingSeq
  try {
    if (!await readList()) return
    if (totalsOpen.value) void loadTotals()
    listReady.value = true
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => t('runs.behy_se_nepodarilo_nacist_p0', { p0: runError(e) })
  } finally {
    if (seq === listLoadingSeq) loading.value = false
  }
}

/** Bumped by every detail load: a reply for an older load is dropped. */
let loadSeq = 0
/** The open run's events are still on their way (the detail may already show). */
const eventsLoading = ref(false)

async function loadDetail(id: string) {
  const seq = ++loadSeq
  const stale = () => seq !== loadSeq || runId.value !== id
  if (detail.value?.run.run_id !== id) {
    // Another run: stop showing the previous one right away.
    detail.value = null
    events.value = []
    cursors = null
  }
  loading.value = true
  eventsLoading.value = true
  errorSource.value = null
  const runReq = fetchRun(id)
  const eventsReq = fetchAllEvents(id)
  // Settled by the awaits below; this only keeps an early failure from being unhandled.
  eventsReq.catch(() => undefined)
  try {
    const data = await runReq
    if (stale()) return
    const sameRun = detail.value?.run.run_id === id
    detail.value = data?.run ? data : null
    if (!detail.value) {
      events.value = []
      cursors = null
      return
    }
    if (!sameRun) cursors = null
    const evts = await eventsReq
    if (stale()) return
    events.value = evts
    cursors = detail.value ? cursorsOf(detail.value, evts) : null
  } catch (e) {
    retryableError.value = isDbBusy(e)
    if (stale()) return
    detail.value = null
    events.value = []
    cursors = null
    errorSource.value = () => t('runs.beh_p0_se_nepodarilo_nacist_p1', { p0: id, p1: runError(e) })
  } finally {
    if (seq === loadSeq) {
      loading.value = false
      eventsLoading.value = false
    }
  }
}

/** Append what is new in the open run (rowid cursors; no full reload, no spinner). */
async function tail(id: string) {
  if (tailing) {
    tailAgain = true
    return
  }
  tailing = true
  try {
    do {
      tailAgain = false
      const seq = loadSeq
      for (;;) {
        const current = detail.value
        if (!current || !cursors || runId.value !== id || current.run.run_id !== id) return
        const open = current.phases.filter((p) => p.status === 'running').map((p) => p.phase_id)
        const page = await fetchRunTail(id, cursors, open)
        if (seq !== loadSeq || runId.value !== id || detail.value?.run.run_id !== id) return
        const merged = applyTail(detail.value, events.value, page)
        detail.value = merged.detail
        events.value = merged.events
        const moved = page.cursors.events > cursors.events
        cursors = { ...page.cursors }
        if (!page.has_more || !moved) break
      }
    } while (tailAgain)
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => t('runs.nove_udalosti_behu_se_nepodarilo_nacist_p0', { p0: runError(e) })
  } finally {
    tailing = false
  }
}

async function refreshList() {
  void loadChains()
  try {
    if (!await readList()) return
    if (totalsOpen.value) void loadTotals()
    listReady.value = true
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => t('runs.behy_se_nepodarilo_nacist_p0', { p0: runError(e) })
  }
}

function onTrace(event: LiveTraceEvent) {
  const id = runId.value
  if (id) {
    const current = detail.value
    if (!current || loading.value) return
    const concerned =
      event.run_ids.includes(id) ||
      event.task_ids.includes(current.run.task_id) ||
      current.phases.some((p) => p.status === 'running')
    if (concerned) void tail(id)
  } else if (!loading.value && (event.runs_changed || event.run_ids.length)) {
    void refreshList()
  }
}

useLive({ trace: onTrace, resync: () => reload() })

function reload() {
  if (runId.value) void loadDetail(runId.value)
  else void loadList()
}

async function onStop() {
  const id = runId.value
  if (!id) return
  stopping.value = true
  try {
    await stopRun(id)
    await loadDetail(id)
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => t('runs.beh_se_nepodarilo_zastavit_p0', { p0: runError(e) })
  } finally {
    stopping.value = false
  }
}

async function onPause(resume: boolean) {
  const id = runId.value
  if (!id) return
  pauseBusy.value = true
  try {
    await (resume ? resumeRun(id) : pauseRun(id))
    await loadDetail(id)
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => resume
      ? t('runs.beh_se_nepodarilo_pustit_dal_p0', { p0: runError(e) })
      : t('runs.beh_se_nepodarilo_pozastavit_p0', { p0: runError(e) })
  } finally {
    pauseBusy.value = false
  }
}

/** `factory task publish`: push the branch of a succeeded run without a PR and open the PR. */
async function onPublish() {
  const id = runId.value
  if (!id) return
  publishing.value = true
  errorSource.value = null
  try {
    const result = await publishRun(id)
    await loadDetail(id)
    const prError = result.pr_error
    if (prError) errorSource.value = () => t('runs.pr_se_nepodarilo_otevrit_p0', { p0: prError })
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => t('runs.pr_se_nepodarilo_otevrit_p0', { p0: runError(e) })
  } finally {
    publishing.value = false
  }
}

function onArchivedView(value: boolean) {
  if (archived.value === value) return
  archived.value = value
  offset.value = 0
  void loadList()
}

/** Run an archive or delete request, then reload the list. */
async function act(failure: () => string, request: () => Promise<unknown>) {
  archiving.value = true
  errorSource.value = null
  try {
    await request()
  } catch (e) {
    retryableError.value = isDbBusy(e)
    errorSource.value = () => `${failure()}: ${runError(e)}`
  } finally {
    archiving.value = false
  }
  await refreshList()
}

function onArchive(id: string) {
  void act(() => t('runs.beh_se_nepodarilo_archivovat'), () => archiveRun(id))
}

function onUnarchive(id: string) {
  void act(() => t('runs.beh_se_nepodarilo_vratit_z_archivu'), () => unarchiveRun(id))
}

async function onDelete(id: string) {
  const ok = await ask(() => ({
    title: t('runs.smazat_beh_z_databaze'),
    message: t('runs.beh_p0_a_cely_jeho_zaznam_se_nevratne_smaze', { p0: id }),
    confirmLabel: t('runs.delete'),
    tone: 'danger',
  }))
  if (ok) await act(() => t('runs.beh_se_nepodarilo_smazat'), () => deleteRun(id))
}

async function onArchiveFinished() {
  const ok = await ask(() => ({
    title: t('runs.archivovat_dokoncene_behy'),
    message:
      t('runs.vsechny_dokoncene_behy_uspesne_s_chybou_prerusene_i_zastavene_se_presunou_do_archivu_'),
    confirmLabel: t('runs.archivovat'),
  }))
  if (ok) await act(() => t('runs.dokoncene_behy_se_nepodarilo_archivovat'), archiveFinishedRuns)
}

async function onDeleteArchived() {
  const ok = await ask(() => ({
    title: t('runs.vymazat_vsechny_archivovane_behy'),
    message: t('runs.vsechny_archivovane_behy_a_jejich_zaznamy_se_nevratne_smazou_z_databaze'),
    confirmLabel: t('runs.vymazat_vsechny'),
    tone: 'danger',
  }))
  if (ok) await act(() => t('runs.archivovane_behy_se_nepodarilo_vymazat'), deleteArchivedRuns)
}

watch(
  runId,
  (id, previous) => {
    if (id !== previous || id === null) reload()
  },
  { immediate: true },
)
</script>

<template>
  <section class="runs-view">
    <div class="view-head">
      <h1>{{ t('runs.behy') }}</h1>
      <BackLink v-if="runId" :href="here('runs')" :label="t('runs.vsechny_behy')" />
      <button type="button" class="refresh" data-test="refresh" :disabled="loading" @click="reload">
        <RefreshCw :size="16" :class="{ spin: loading }" /> {{ t('runs.obnovit') }} </button>
    </div>
    <p v-if="error" class="error-bar" data-test="error">
      {{ error }}
      <button v-if="retryableError" type="button" class="retry" data-test="retry" @click="reload"> {{ t('runs.zkusit_znovu') }} </button>
    </p>

    <template v-if="runId">
      <RunDetail
        v-if="detail"
        :detail="detail"
        :events="events"
        :phase-id="phaseId"
        :events-loading="eventsLoading"
        :stopping="stopping"
        :pause-busy="pauseBusy"
        :publishing="publishing"
        @stop="onStop"
        @pause="onPause(false)"
        @resume="onPause(true)"
        @publish="onPublish"
        @retried="reload"
        @cancelled="reload"
        @done="reload"
      />
      <p v-else-if="loading" class="faint" data-test="detail-loading"> {{ t('runs.nacitam_beh') }} <span class="run-id">{{ runId }}</span>…
      </p>
    </template>
    <template v-else>
      <ChainPanel v-if="!archived" :chains="chains" :dismissing="dismissing" @dismiss="onDismissChain" />
      <div class="run-filters">
        <label>{{ t('runs.stav') }} <SelectMenu v-model="stateFilter" data-test="state-filter"
          :label="t('runs.stav_behu')" :options="stateOptions" @update:model-value="filterList" /></label>
        <label>{{ t('runs.task') }} <SelectMenu v-model="taskFilter" data-test="task-filter"
          :label="t('runs.task_behu')" :options="taskOptions" @update:model-value="filterList" /></label>
      </div>
      <RunsList
        :runs="runs"
        :ready="listReady"
        :loading="loading"
        :archived="archived"
        :busy="archiving"
        @update:archived="onArchivedView"
        @archive="onArchive"
        @unarchive="onUnarchive"
        @delete="onDelete"
        @archive-finished="onArchiveFinished"
        @delete-archived="onDeleteArchived"
      />
      <nav v-if="listReady" class="run-pages" :aria-label="t('runs.stranky_behu')">
        <button type="button" data-test="previous-page" :disabled="loading || offset === 0" @click="changePage(-1)">{{ t('runs.predchozi') }}</button>
        <span data-test="page-count">{{ t('runs.pageCount', { first: totalRuns ? offset + 1 : 0, last: offset + runs.length, total: totalRuns }) }}</span>
        <button type="button" data-test="next-page" :disabled="loading || offset + runs.length >= totalRuns" @click="changePage(1)">{{ t('runs.dalsi') }}</button>
      </nav>
      <CostTotals
        v-if="listReady"
        :open="totalsOpen"
        :totals="totals"
        :loading="totalsLoading"
        :error="totalsError"
        @toggle="toggleTotals"
      />
    </template>
    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />
  </section>
</template>

<style scoped>
.run-filters, .run-pages {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin: 16px 0;
}
.run-filters label { display: flex; align-items: center; gap: 8px; }
.runs-view {
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
</style>

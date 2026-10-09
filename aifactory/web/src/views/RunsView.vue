<script setup lang="ts">
import { errorText } from '../lib/format'
import { computed, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import BackLink from '@/components/ui/BackLink.vue'
import CostTotals from '@/components/runs/CostTotals.vue'
import RunDetail from '@/components/runs/RunDetail.vue'
import RunsList from '@/components/runs/RunsList.vue'
import ChainPanel from '@/components/runs/ChainPanel.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { ApiError, isDbBusyText } from '@/lib/api'
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
const error = ref<string | null>(null)

const runs = ref<RunSummary[]>([])
/** Auto-continue chains; a failure to load them leaves the list of runs alone. */
const chains = ref<Chain[]>([])
/** The chain being hidden. */
const dismissing = ref<string | null>(null)
/** Cost totals: folded by default, loaded when the section opens (and refreshed while open). */
const totals = ref<RunTotals | null>(null)
const totalsOpen = ref(false)
const totalsLoading = ref(false)
const totalsError = ref<string | null>(null)
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

function message(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return errorText(e)
}

async function loadTotals() {
  totalsLoading.value = true
  totalsError.value = null
  try {
    totals.value = await fetchRunTotals()
  } catch (e) {
    totalsError.value = `Náklady se nepodařilo načíst: ${message(e)}`
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
    error.value = `Řetěz se nepodařilo skrýt: ${message(e)}`
  } finally {
    dismissing.value = null
  }
}

async function loadList() {
  loading.value = true
  error.value = null
  void loadChains()
  try {
    const data = await fetchRuns(archived.value)
    runs.value = Array.isArray(data?.runs) ? data.runs : []
    if (totalsOpen.value) void loadTotals()
    listReady.value = true
  } catch (e) {
    error.value = `Běhy se nepodařilo načíst: ${message(e)}`
  } finally {
    loading.value = false
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
  error.value = null
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
    if (stale()) return
    detail.value = null
    events.value = []
    cursors = null
    error.value = `Běh ${id} se nepodařilo načíst: ${message(e)}`
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
    error.value = `Nové události běhu se nepodařilo načíst: ${message(e)}`
  } finally {
    tailing = false
  }
}

async function refreshList() {
  void loadChains()
  try {
    const data = await fetchRuns(archived.value)
    runs.value = Array.isArray(data?.runs) ? data.runs : []
    if (totalsOpen.value) void loadTotals()
    listReady.value = true
  } catch (e) {
    error.value = `Běhy se nepodařilo načíst: ${message(e)}`
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
    error.value = `Běh se nepodařilo zastavit: ${message(e)}`
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
    error.value = resume
      ? `Běh se nepodařilo pustit dál: ${message(e)}`
      : `Běh se nepodařilo pozastavit: ${message(e)}`
  } finally {
    pauseBusy.value = false
  }
}

/** `factory task publish`: push the branch of a succeeded run without a PR and open the PR. */
async function onPublish() {
  const id = runId.value
  if (!id) return
  publishing.value = true
  error.value = null
  try {
    const result = await publishRun(id)
    await loadDetail(id)
    if (result.pr_error) error.value = `PR se nepodařilo otevřít: ${result.pr_error}`
  } catch (e) {
    error.value = `PR se nepodařilo otevřít: ${message(e)}`
  } finally {
    publishing.value = false
  }
}

function onArchivedView(value: boolean) {
  if (archived.value === value) return
  archived.value = value
  void loadList()
}

/** Run an archive or delete request, then reload the list. */
async function act(failure: string, request: () => Promise<unknown>) {
  archiving.value = true
  error.value = null
  try {
    await request()
  } catch (e) {
    error.value = `${failure}: ${message(e)}`
  } finally {
    archiving.value = false
  }
  await refreshList()
}

function onArchive(id: string) {
  void act('Běh se nepodařilo archivovat', () => archiveRun(id))
}

function onUnarchive(id: string) {
  void act('Běh se nepodařilo vrátit z archivu', () => unarchiveRun(id))
}

async function onDelete(id: string) {
  const ok = await ask({
    title: 'Smazat běh z databáze?',
    message: `Běh ${id} a celý jeho záznam se nevratně smaže.`,
    confirmLabel: 'Smazat',
    tone: 'danger',
  })
  if (ok) await act('Běh se nepodařilo smazat', () => deleteRun(id))
}

async function onArchiveFinished() {
  const ok = await ask({
    title: 'Archivovat dokončené běhy?',
    message:
      'Všechny dokončené běhy (úspěšné, s chybou, přerušené i zastavené) se přesunou do archivu. Z archivu je lze kdykoli vrátit.',
    confirmLabel: 'Archivovat',
  })
  if (ok) await act('Dokončené běhy se nepodařilo archivovat', archiveFinishedRuns)
}

async function onDeleteArchived() {
  const ok = await ask({
    title: 'Vymazat všechny archivované běhy?',
    message: 'Všechny archivované běhy a jejich záznamy se nevratně smažou z databáze.',
    confirmLabel: 'Vymazat všechny',
    tone: 'danger',
  })
  if (ok) await act('Archivované běhy se nepodařilo vymazat', deleteArchivedRuns)
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
      <h1>Běhy</h1>
      <BackLink v-if="runId" :href="here('runs')" label="všechny běhy" />
      <button type="button" class="refresh" data-test="refresh" :disabled="loading" @click="reload">
        <RefreshCw :size="16" :class="{ spin: loading }" /> Obnovit
      </button>
    </div>
    <p v-if="error" class="error-bar" data-test="error">
      {{ error }}
      <button v-if="isDbBusyText(error)" type="button" class="retry" data-test="retry" @click="reload">
        Zkusit znovu
      </button>
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
      />
      <p v-else-if="loading" class="faint" data-test="detail-loading">
        Načítám běh <span class="run-id">{{ runId }}</span>…
      </p>
    </template>
    <template v-else>
      <ChainPanel v-if="!archived" :chains="chains" :dismissing="dismissing" @dismiss="onDismissChain" />
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

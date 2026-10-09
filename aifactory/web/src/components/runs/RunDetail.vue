<script setup lang="ts">
import { computed } from 'vue'
import { CircleStop, Pause, Play, Upload } from 'lucide-vue-next'
import { useNow } from '@/lib/clock'
import { fmtTime, ts } from '@/lib/format'
import { reviewHref, runHref, taskHref } from '@/lib/router'
import {
  bySeq,
  canPublish,
  prStateLabel,
  shownState,
  startedByTip,
  type RunDetail,
  type TraceEvent,
} from '@/lib/runs'
import { isLive } from '@/lib/waterfall'
import { useConfirm } from '@/lib/confirm'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'
import PhaseDetail from './PhaseDetail.vue'
import RunWaterfall from './RunWaterfall.vue'
import StatChip from './StatChip.vue'
import StatusChip from './StatusChip.vue'

const props = defineProps<{
  detail: RunDetail
  events: TraceEvent[]
  /** The events are still on their way: shown as loading, not as none. */
  eventsLoading?: boolean
  phaseId?: string | null
  stopping?: boolean
  /** A pause or resume request is on its way. */
  pauseBusy?: boolean
  /** A publish (push and PR) request is on its way. */
  publishing?: boolean
}>()

const emit = defineEmits<{ stop: []; pause: []; resume: []; publish: [] }>()

const run = computed(() => props.detail.run)
const phases = computed(() => [...(props.detail.phases ?? [])].sort(bySeq))
// Running blocks and durations grow every second without reloading anything.
const live = computed(() => isLive(props.detail))
const now = useNow(() => live.value)
const runtime = computed(() => {
  const start = ts(run.value.started_at)
  if (run.value.state === 'running' && Number.isFinite(start)) return Math.max(now.value - start, 0) / 1000
  return run.value.duration_s
})
// A running run without a pause can be paused; a paused (or pausing) one resumed.
const canPause = computed(() => run.value.state === 'running' && !run.value.pause)
const canResume = computed(() => run.value.state === 'running' && !!run.value.pause)
// No phase is preselected: the panel shows only once the user picks one.
const selected = computed(() => phases.value.find((p) => p.phase_id === props.phaseId) ?? null)
const phaseGates = computed(() =>
  (props.detail.gates ?? []).filter((g) => g.phase_id === selected.value?.phase_id),
)
const phaseEnvelopes = computed(() =>
  (props.detail.envelopes ?? []).filter((e) => e.phase_id === selected.value?.phase_id),
)
const phaseEvents = computed(() =>
  props.events.filter((e) => e.phase_id === selected.value?.phase_id),
)

function onClose() {
  window.location.hash = runHref(run.value.run_id)
}

const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

async function onStop() {
  const ok = await ask({
    title: `Zastavit běh ${run.value.run_id} tasku ${run.value.task_id}?`,
    tone: 'danger',
  })
  if (ok) emit('stop')
}
</script>

<template>
  <div class="run-detail">
    <header class="head">
      <div class="title">
        <h2 data-test="task-label">
          <a class="task-id" :href="taskHref(run.task_id)" data-test="task-link">{{ run.task_id }}</a
          ><span v-if="run.task_title" class="dim">{{ ' ' + run.task_title }}</span>
        </h2>
        <StatusChip :status="shownState(run)" />
        <button
          v-if="canPause"
          type="button"
          class="pause"
          data-test="pause-run"
          :disabled="pauseBusy"
          :aria-busy="pauseBusy || undefined"
          @click="emit('pause')"
        >
          <Spinner v-if="pauseBusy" />
          <Pause v-else :size="16" /> Pauza
        </button>
        <button
          v-if="canResume"
          type="button"
          class="pause"
          data-test="resume-run"
          :disabled="pauseBusy"
          :aria-busy="pauseBusy || undefined"
          @click="emit('resume')"
        >
          <Spinner v-if="pauseBusy" />
          <Play v-else :size="16" /> Pokračovat
        </button>
        <button
          v-if="run.state === 'running'"
          type="button"
          class="stop"
          data-test="stop-run"
          :disabled="stopping"
          :aria-busy="stopping || undefined"
          @click="onStop"
        >
          <Spinner v-if="stopping" />
          <CircleStop v-else :size="16" /> Zastavit
        </button>
      </div>
      <dl class="meta">
        <div><dt>Běh</dt><dd class="mono">{{ run.run_id }}</dd></div>
        <div><dt>Workflow</dt><dd>{{ run.workflow ?? '—' }}</dd></div>
        <div><dt>Větev</dt><dd class="mono">{{ run.branch }}</dd></div>
        <div><dt>Začátek</dt><dd>{{ fmtTime(run.started_at) }}</dd></div>
        <div><dt>Konec</dt><dd>{{ fmtTime(run.ended_at) }}</dd></div>
        <div>
          <dt>Spustil</dt>
          <dd data-test="started-by">{{ startedByTip(run.started_by) }}</dd>
        </div>
        <div>
          <dt>PR</dt>
          <dd>
            <template v-if="run.pr">
              <a :href="run.pr.url" target="_blank" rel="noopener" data-test="pr-link">
                #{{ run.pr.pr_id }} ({{ prStateLabel(run.pr.state) }})
              </a>
              <a :href="reviewHref(run.task_id)" class="review-link" data-test="pr-review">Review</a>
            </template>
            <span v-else class="faint">—</span>
            <span v-if="!run.pr && run.pr_error" class="auto-error" data-test="pr-error"
              >PR nevznikl: {{ run.pr_error }}</span
            >
            <button
              v-if="canPublish(run)"
              type="button"
              class="publish"
              data-test="publish-run"
              aria-label="Pushnout větev a otevřít PR (factory task publish)"
              :disabled="publishing"
              :aria-busy="publishing || undefined"
              @click="emit('publish')"
            >
              <Spinner v-if="publishing" />
              <Upload v-else :size="14" /> Publikovat
            </button>
            <span
              v-if="run.pr?.merged_by === 'auto-merge'"
              class="merged-by"
              data-test="pr-merged-by"
              >sloučil auto-merge</span
            >
            <span
              v-else-if="run.pr?.state === 'open' && run.pr.auto_merge_error"
              class="auto-error"
              data-test="pr-auto-merge-error"
              >auto-merge nesloučil: {{ run.pr.auto_merge_error }}</span
            >
          </dd>
        </div>
      </dl>
      <div class="stats">
        <StatChip kind="runtime" :value="runtime" />
        <StatChip kind="tokens" :value="run.tokens" />
        <StatChip kind="cost" :value="run.cost" />
        <StatChip kind="read" :value="detail.usage?.read" />
        <StatChip kind="written" :value="detail.usage?.written" />
      </div>
      <p v-if="run.error" class="error-bar" data-test="run-error">{{ run.error }}</p>
    </header>

    <h3>Fáze</h3>
    <RunWaterfall :detail="detail" :events="events" :phase-id="phaseId" :now="now" />
    <p v-if="eventsLoading" class="faint hint" data-test="events-loading">Načítám události…</p>
    <p v-if="phases.length && !selected" class="faint hint" data-test="phase-hint">Vyber fázi pro detail.</p>

    <PhaseDetail
      v-if="selected"
      class="phase-panel"
      :run-id="run.run_id"
      :phase="selected"
      :request="detail.session?.request ?? null"
      :gates="phaseGates"
      :envelopes="phaseEnvelopes"
      :events="phaseEvents"
      :events-loading="eventsLoading"
      @close="onClose"
    />

    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />
  </div>
</template>

<style scoped>
.head {
  margin-bottom: 22px;
}

.title {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

h2 {
  margin: 0;
  font-size: 22px;
}

h3 {
  margin: 18px 0 10px;
  font-size: 18px;
}

.task-id,
.mono {
  font-family: var(--mono);
}

a.task-id {
  color: inherit;
  text-decoration: none;
}

a.task-id:hover {
  text-decoration: underline;
}

.review-link {
  margin-left: 8px;
}

.pause {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--cyan);
  font: inherit;
  cursor: pointer;
}

.pause:disabled {
  opacity: 0.6;
  cursor: default;
}

.pause + .stop {
  margin-left: 0;
}

.stop {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 6px 14px;
  border: 1px solid rgba(255, 111, 103, 0.55);
  border-radius: 8px;
  background: rgba(255, 111, 103, 0.1);
  color: var(--red);
  font: inherit;
  cursor: pointer;
}

.publish {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 10px;
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.publish:disabled {
  opacity: 0.6;
  cursor: default;
}

.stop:disabled {
  opacity: 0.6;
  cursor: default;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 28px;
  margin: 14px 0;
}

.meta div {
  display: flex;
  gap: 8px;
}

dt {
  color: var(--faint);
}

dd {
  margin: 0;
}

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.phase-panel {
  margin-top: 22px;
}

.hint {
  margin: 10px 0 0;
}

.merged-by {
  margin-left: 6px;
  color: var(--cyan);
  font-size: 13px;
}

.auto-error {
  display: block;
  color: var(--amber);
  font-size: 13px;
}
</style>

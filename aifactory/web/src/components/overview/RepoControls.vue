<script setup lang="ts">
// The factory controls of a repo on the overview: Spustit továrnu (ready tasks into the free
// parallel slots), Pauza / Pokračovat / Stop for every running run, the progress of a stop or
// pause ("dobíhá" → "Zastaveno"/"Pozastaveno") and the tasks per board state. The progress
// comes from the overview, which reloads every 2 s; a finished request emits `changed`.
import { computed, ref } from 'vue'
import { CircleStop, Pause, Play } from 'lucide-vue-next'
import {
  controlPause,
  controlResume,
  controlStart,
  controlStop,
  type FactoryStartResult,
  type OverviewRepo,
} from '@/lib/api'
import { useConfirm } from '@/lib/confirm'
import { errorText, plural } from '@/lib/format'
import {
  canPause,
  canResume,
  canStart,
  canStop,
  controlErrors,
  controlStatus,
  taskSummary,
} from '@/lib/overview'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = withDefaults(defineProps<{ repo: OverviewRepo; compact?: boolean }>(), { compact: false })
const emit = defineEmits<{ changed: [] }>()

const starting = ref(false)
const pausing = ref(false)
const resuming = ref(false)
const stopping = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

const summary = computed(() => taskSummary(props.repo))
const status = computed(() => controlStatus(props.repo))
const errors = computed(() => controlErrors(props.repo))
const factory = computed(() => props.repo.factory ?? null)
const showStart = computed(() => canStart(props.repo))
const showPause = computed(() => canPause(props.repo))
const showResume = computed(() => canResume(props.repo))
const showStop = computed(() => canStop(props.repo))
const anything = computed(
  () =>
    showStart.value ||
    showPause.value ||
    showResume.value ||
    showStop.value ||
    status.value !== null ||
    summary.value.length > 0 ||
    message.value !== null ||
    error.value !== null,
)

const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

function startMessage(result: FactoryStartResult): string {
  const n = result.started.length
  if (n > 0) return `Spuštěno ${n} ${plural(n, 'běh', 'běhy', 'běhů')}`
  const why = result.skipped
    .slice(0, 3)
    .map((s) => `${s.task_id} (${s.detail || s.reason})`)
    .join(', ')
  return `Nic se nespustilo${why ? `: ${why}` : ''}`
}

async function act(busy: typeof starting, call: () => Promise<void>) {
  busy.value = true
  error.value = null
  message.value = null
  try {
    await call()
  } catch (err) {
    error.value = errorText(err)
  } finally {
    busy.value = false
    emit('changed')
  }
}

function onStart() {
  return act(starting, async () => {
    message.value = startMessage(await controlStart(props.repo.id))
  })
}

function onPause() {
  return act(pausing, async () => {
    await controlPause(props.repo.id)
  })
}

function onResume() {
  return act(resuming, async () => {
    await controlResume(props.repo.id)
  })
}

async function onStop() {
  const n = props.repo.running.filter((r) => r.process !== 'ended').length
  const ok = await ask({
    title: `Zastavit všechny běhy repozitáře ${props.repo.name}?`,
    message: `Zastaví se ${n} ${plural(n, 'běh', 'běhy', 'běhů')}; řetězy auto-continue už nic dalšího nespustí.`,
    confirmLabel: 'Zastavit',
    tone: 'danger',
  })
  if (!ok) return
  await act(stopping, async () => {
    await controlStop(props.repo.id)
  })
}
</script>

<template>
  <div v-if="anything" class="repo-controls" :class="{ compact }" data-test="factory-controls">
    <div class="buttons">
      <button
        v-if="showStart"
        type="button"
        class="start"
        data-test="factory-start"
        :disabled="starting"
        :aria-busy="starting || undefined"
        @click="onStart"
      >
        <Spinner v-if="starting" />
        <Play v-else :size="14" aria-hidden="true" /> Spustit továrnu
      </button>
      <button
        v-if="showPause"
        type="button"
        class="pause"
        data-test="factory-pause"
        :disabled="pausing"
        :aria-busy="pausing || undefined"
        @click="onPause"
      >
        <Spinner v-if="pausing" />
        <Pause v-else :size="14" aria-hidden="true" /> Pauza
      </button>
      <button
        v-if="showResume"
        type="button"
        class="pause"
        data-test="factory-resume"
        :disabled="resuming"
        :aria-busy="resuming || undefined"
        @click="onResume"
      >
        <Spinner v-if="resuming" />
        <Play v-else :size="14" aria-hidden="true" /> Pokračovat
      </button>
      <button
        v-if="showStop"
        type="button"
        class="stop"
        data-test="factory-stop"
        :disabled="stopping"
        :aria-busy="stopping || undefined"
        @click="onStop"
      >
        <Spinner v-if="stopping" />
        <CircleStop v-else :size="14" aria-hidden="true" /> Stop
      </button>
      <span
        v-if="status"
        class="status"
        :class="status.kind"
        data-test="factory-control-status"
        :data-kind="status.kind"
      >
        <Spinner v-if="status.kind === 'stopping' || status.kind === 'pausing'" />
        {{ status.text }}
      </span>
    </div>

    <p v-if="message" class="message" data-test="factory-start-message">{{ message }}</p>
    <p v-if="error" class="error" data-test="factory-control-error">{{ error }}</p>
    <p v-for="(line, i) in errors" :key="i" class="error" data-test="factory-control-errors">{{ line }}</p>

    <div v-if="summary.length || factory" class="summary">
      <span v-if="summary.length" class="tasks" data-test="task-summary">
        <span
          v-for="item in summary"
          :key="item.state"
          class="chip"
          data-test="task-summary-item"
          :data-state="item.state"
        >{{ item.label }} <b>{{ item.count }}</b></span>
      </span>
      <span v-if="factory && factory.max_parallel_runs !== null" class="slots" data-test="factory-slots">
        Sloty: {{ factory.running }}/{{ factory.max_parallel_runs }}
      </span>
    </div>

    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />
  </div>
</template>

<style scoped>
.repo-controls {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.repo-controls.compact {
  flex: 1 1 100%;
}

.buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.buttons:empty {
  display: none;
}

button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 8px;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: default;
}

.start {
  border: 1px solid rgba(80, 200, 120, 0.6);
  background: rgba(80, 200, 120, 0.14);
  color: var(--green);
  font-weight: 600;
}

.pause {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--cyan);
}

.stop {
  border: 1px solid rgba(255, 111, 103, 0.55);
  background: rgba(255, 111, 103, 0.1);
  color: var(--red);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--amber);
  font-size: 14px;
}

.status.stopped,
.status.paused {
  color: var(--dim);
}

.message {
  margin: 0;
  color: var(--dim);
  font-size: 13px;
}

.error {
  margin: 0;
  color: var(--red);
  font-size: 13px;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  font-size: 13px;
  color: var(--dim);
}

.tasks {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
}

.chip b {
  color: var(--text);
  font-weight: 600;
}

.slots {
  color: var(--faint);
}
</style>

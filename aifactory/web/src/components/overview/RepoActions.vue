<script setup lang="ts">
import { t } from '@/lib/i18n'
// The factory buttons of a repo on the overview, shown as small icons in the top right corner of a
// card or a calm row: Spustit továrnu (ready tasks into the free parallel slots), Pauza / Pokračovat
// / Stop for every running run. The action name is in the tooltip and in aria-label. A finished
// request emits `feedback` (the message or the error, shown by RepoControls) and `changed`.
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
import { deferredError, skipReason } from '@/lib/dashboardMessages'
import { canPause, canResume, canStart, canStop } from '@/lib/overview'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { NO_FEEDBACK, type ControlFeedback } from './feedback'

const props = defineProps<{ repo: OverviewRepo }>()
const emit = defineEmits<{ changed: []; feedback: [feedback: ControlFeedback] }>()

const stopCount = ref(0)
const starting = ref(false)
const pausing = ref(false)
const resuming = ref(false)
const stopping = ref(false)

const showStart = computed(() => canStart(props.repo))
const showPause = computed(() => canPause(props.repo))
const showResume = computed(() => canResume(props.repo))
const showStop = computed(() => canStop(props.repo))
const anything = computed(() => showStart.value || showPause.value || showResume.value || showStop.value)

const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

function startMessage(result: FactoryStartResult): string {
  const n = result.started.length
  if (n > 0) return t('dashboard.started', { count: n }, n)
  const why = result.skipped
    .slice(0, 3)
    .map((s) => `${s.task_id} (${skipReason(s.reason)})`)
    .join(', ')
  return `${t('dashboard.nothingStarted')}${why ? `: ${why}` : ''}`
}

async function act(busy: typeof starting, call: () => Promise<ControlFeedback | null>) {
  busy.value = true
  emit('feedback', NO_FEEDBACK)
  try {
    emit('feedback', await call() ?? NO_FEEDBACK)
  } catch (err) {
    emit('feedback', { message: null, error: deferredError(err) })
  } finally {
    busy.value = false
    emit('changed')
  }
}

function onStart() {
  return act(starting, async () => {
    const result = await controlStart(props.repo.id)
    return { message: () => startMessage(result), error: null,
      diagnostics: result.skipped.map(s => `${s.task_id}: ${s.detail}`).join('\n') }
  })
}

function onPause() {
  return act(pausing, async () => {
    await controlPause(props.repo.id)
    return null
  })
}

function onResume() {
  return act(resuming, async () => {
    await controlResume(props.repo.id)
    return null
  })
}

async function onStop() {
  const n = props.repo.running.filter((r) => r.process !== 'ended').length
  stopCount.value = n
  const ok = await ask({
    title: t('dashboard.stopTitle', { name: props.repo.name }),
    message: t('dashboard.stopBody', { count: n }, n),
    confirmLabel: t('dashboard.stopConfirm'),
    cancelLabel: t('common.cancel'),
    tone: 'danger',
  })
  if (!ok) return
  await act(stopping, async () => {
    await controlStop(props.repo.id)
    return null
  })
}
</script>

<template>
  <div v-if="anything" class="repo-actions" data-test="factory-actions">
    <Tooltip v-if="showStart" :text="t('dashboard.start')">
      <button
        type="button"
        class="start"
        data-test="factory-start"
        :aria-label="t('dashboard.start')"
        :disabled="starting"
        :aria-busy="starting || undefined"
        @click="onStart"
      >
        <Spinner v-if="starting" />
        <Play v-else :size="14" aria-hidden="true" />
      </button>
    </Tooltip>
    <Tooltip v-if="showPause" :text="t('dashboard.pause')">
      <button
        type="button"
        class="pause"
        data-test="factory-pause"
        :aria-label="t('dashboard.pause')"
        :disabled="pausing"
        :aria-busy="pausing || undefined"
        @click="onPause"
      >
        <Spinner v-if="pausing" />
        <Pause v-else :size="14" aria-hidden="true" />
      </button>
    </Tooltip>
    <Tooltip v-if="showResume" :text="t('dashboard.resume')">
      <button
        type="button"
        class="pause"
        data-test="factory-resume"
        :aria-label="t('dashboard.resume')"
        :disabled="resuming"
        :aria-busy="resuming || undefined"
        @click="onResume"
      >
        <Spinner v-if="resuming" />
        <Play v-else :size="14" aria-hidden="true" />
      </button>
    </Tooltip>
    <Tooltip v-if="showStop" :text="t('dashboard.stop')">
      <button
        type="button"
        class="stop"
        data-test="factory-stop"
        :aria-label="t('dashboard.stop')"
        :disabled="stopping"
        :aria-busy="stopping || undefined"
        @click="onStop"
      >
        <Spinner v-if="stopping" />
        <CircleStop v-else :size="14" aria-hidden="true" />
      </button>
    </Tooltip>

    <ConfirmDialog v-bind="dialog"
      :title="t('dashboard.stopTitle', { name: repo.name })"
      :message="t('dashboard.stopBody', { count: stopCount }, stopCount)"
      :confirm-label="t('dashboard.stopConfirm')" :cancel-label="t('common.cancel')" @confirm="onDialogConfirm" @cancel="onDialogCancel" />
  </div>
</template>

<style scoped>
.repo-actions {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 4px;
}

button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border-radius: 6px;
  font: inherit;
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
</style>

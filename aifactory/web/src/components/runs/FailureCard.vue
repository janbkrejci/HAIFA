<script setup lang="ts">
// The failure card at the top of a run detail: the kind of the failure in Czech, one
// sentence and the facts from the run's `failure_detail`, the whole error text, and the
// actions that exist for the kind (lib/failure.ts). A writes_violation or writes_needed offers
// „Povolit tyto cesty a pokračovat“ (`factory task retry --allow-writes`; for a ci-fix run
// „Povolit tyto cesty a schválit znovu“, `factory task approve --allow-writes`) for the paths writes can allow
// and says why the others stay forbidden (GET /api/runs/{id}/allow-writes). A nothing_to_do
// run offers „Hotovo“: the task is done in base without changes (POST /api/runs/{id}/done). A
// quota run offers „Pokračovat s jiným harnessem“ (SwitchHarnessButton, `task retry --harness`).
// A blocked run is no failure: its card has its own colour and links to the blocking tasks.
import { computed, ref, watch } from 'vue'
import { Ban, CircleCheck, ShieldCheck } from 'lucide-vue-next'
import { editTask } from '@/lib/backlog'
import { useConfirm } from '@/lib/confirm'
import { allowWritesReason, failureCard, type FailurePhase } from '@/lib/failure'
import { errorText } from '@/lib/format'
import { taskHref } from '@/lib/router'
import {
  allowWritesAndRetry,
  allowWritesPlan,
  canRetry,
  markRunDone,
  type AllowWritesPlan,
  type RunSummary,
} from '@/lib/runs'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'
import RetryRunButton from './RetryRunButton.vue'
import SwitchHarnessButton from './SwitchHarnessButton.vue'

const props = defineProps<{ run: RunSummary; phases?: readonly FailurePhase[] }>()
const emit = defineEmits<{ retried: []; cancelled: []; done: [] }>()

const card = computed(() => failureCard(props.run, props.phases ?? []))
// a ci-fix run is never retried: its PR is approved again (factory task approve)
const isCiFix = computed(() => props.run.workflow === 'ci-fix')
const canContinue = computed(
  () => !!card.value?.actions.includes('continue') && canRetry(props.run) && !isCiFix.value,
)
const canCancel = computed(() => !!card.value?.actions.includes('cancel_task'))
const canMarkDone = computed(() => !!card.value?.actions.includes('mark_done'))
const canSwitch = computed(() => !!card.value?.actions.includes('switch_harness') && canRetry(props.run))
const wantsAllow = computed(() => !!card.value?.actions.includes('allow_writes') && canRetry(props.run))

const plan = ref<AllowWritesPlan | null>(null)
const allowing = ref(false)
const allowed = ref(false)
const allowError = ref<string | null>(null)
const canAllow = computed(() => wantsAllow.value && !!plan.value?.allow.length)
const refused = computed(() =>
  (plan.value?.refused ?? []).map((r) => `${r.path} — ${allowWritesReason(r.reason, r.message)}`),
)

watch(
  () => [props.run.run_id, wantsAllow.value] as const,
  async ([runId, wants], _old, onCleanup) => {
    plan.value = null
    if (!wants) return
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    try {
      plan.value = await allowWritesPlan(runId, controller.signal)
    } catch {
      plan.value = null // the card still offers Pokračovat and Zrušit task
    }
  },
  { immediate: true },
)
// The whole error, when it says more than the sentence of the card.
const fullError = computed(() => {
  const error = props.run.error?.trim()
  if (!error || !card.value) return null
  return card.value.sentence.replace(/\.$/, '') === error.replace(/\.$/, '') ? null : error
})

const cancelling = ref(false)
const cancelled = ref(false)
const cancelError = ref<string | null>(null)
const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

async function onAllowWrites() {
  const paths = plan.value?.allow ?? []
  if (!paths.length) return
  const ok = await ask({
    title: `Povolit cesty tasku ${props.run.task_id}?`,
    message: isCiFix.value
      ? `Do writes tasku přibude ${paths.join(', ')}. Změna backlogu se commitne do base a schválení PR se spustí znovu.`
      : `Do writes tasku přibude ${paths.join(', ')}. Změna backlogu se commitne do base a běh pokračuje.`,
    confirmLabel: isCiFix.value ? 'Povolit a schválit' : 'Povolit a pokračovat',
    cancelLabel: 'Ponechat',
  })
  if (!ok) return
  allowing.value = true
  allowError.value = null
  try {
    await allowWritesAndRetry(props.run.run_id)
    allowed.value = true
    emit('retried')
  } catch (e) {
    allowError.value = `Cesty se nepodařilo povolit: ${errorText(e)}`
  } finally {
    allowing.value = false
  }
}

const marking = ref(false)
const marked = ref(false)
const markError = ref<string | null>(null)

async function onMarkDone() {
  const ok = await ask({
    title: `Označit task ${props.run.task_id} jako hotový?`,
    message: 'Task dostane stav hotovo v base se záznamem „bez změn“ a důvodem agenta. PR nevznikne.',
    confirmLabel: 'Hotovo',
    cancelLabel: 'Ponechat',
  })
  if (!ok) return
  marking.value = true
  markError.value = null
  try {
    await markRunDone(props.run.run_id)
    marked.value = true
    emit('done')
  } catch (e) {
    markError.value = `Task se nepodařilo označit jako hotový: ${errorText(e)}`
  } finally {
    marking.value = false
  }
}

async function onCancelTask() {
  const ok = await ask({
    title: `Zrušit task ${props.run.task_id}?`,
    message: 'Zrušený task se už nespouští. Běh i jeho větev zůstanou.',
    confirmLabel: 'Zrušit task',
    cancelLabel: 'Ponechat',
    tone: 'danger',
  })
  if (!ok) return
  cancelling.value = true
  cancelError.value = null
  try {
    await editTask(props.run.task_id, { status: 'cancelled' })
    cancelled.value = true
    emit('cancelled')
  } catch (e) {
    cancelError.value = `Task se nepodařilo zrušit: ${errorText(e)}`
  } finally {
    cancelling.value = false
  }
}
</script>

<template>
  <section v-if="card" class="failure-card" data-test="failure-card" :data-kind="card.kind">
    <header class="card-head">
      <h3 data-test="failure-kind">{{ card.label }}</h3>
      <div class="actions">
        <button
          v-if="canAllow"
          type="button"
          class="allow-writes"
          data-test="allow-writes"
          :disabled="allowing || allowed"
          :aria-busy="allowing || undefined"
          @click="onAllowWrites"
        >
          <Spinner v-if="allowing" />
          <ShieldCheck v-else :size="14" /> {{ isCiFix ? 'Povolit tyto cesty a schválit znovu' : 'Povolit tyto cesty a pokračovat' }}
        </button>
        <button
          v-if="canMarkDone"
          type="button"
          class="mark-done"
          data-test="mark-done"
          :disabled="marking || marked || cancelled"
          :aria-busy="marking || undefined"
          @click="onMarkDone"
        >
          <Spinner v-if="marking" />
          <CircleCheck v-else :size="14" /> Hotovo
        </button>
        <SwitchHarnessButton v-if="canSwitch" :run-id="run.run_id" @started="emit('retried')" />
        <RetryRunButton v-if="canContinue" :run-id="run.run_id" label="Pokračovat" @started="emit('retried')" />
        <button
          v-if="canCancel"
          type="button"
          class="cancel-task"
          data-test="cancel-task"
          :disabled="cancelling || cancelled || marked"
          :aria-busy="cancelling || undefined"
          @click="onCancelTask"
        >
          <Spinner v-if="cancelling" />
          <Ban v-else :size="14" /> Zrušit task
        </button>
      </div>
    </header>
    <p class="sentence" data-test="failure-sentence">{{ card.sentence }}</p>
    <div v-for="fact in card.facts" :key="fact.id" class="fact" :data-fact="fact.id">
      <h4>{{ fact.label }}</h4>
      <ul :class="{ mono: fact.mono }">
        <li v-for="(item, i) in fact.items" :key="i" data-test="failure-item">
          <a v-if="fact.tasks" :href="taskHref(item)" data-test="blocker-link">{{ item }}</a>
          <template v-else>{{ item }}</template>
        </li>
      </ul>
    </div>
    <div v-if="canAllow" class="fact" data-fact="allow">
      <h4>Akce přidá do writes</h4>
      <ul class="mono">
        <li v-for="path in plan?.allow ?? []" :key="path" data-test="failure-item">{{ path }}</li>
      </ul>
    </div>
    <div v-if="wantsAllow && refused.length" class="fact" data-fact="refused">
      <h4>Tyto cesty akce nepovolí</h4>
      <ul>
        <li v-for="(item, i) in refused" :key="i" data-test="failure-item">{{ item }}</li>
      </ul>
    </div>
    <details v-if="fullError" class="full-error">
      <summary>Celá chybová zpráva</summary>
      <pre data-test="run-error">{{ fullError }}</pre>
    </details>
    <p v-if="allowed" class="done" data-test="allow-done">
      Writes tasku {{ run.task_id }} rozšířené, {{ isCiFix ? 'schválení PR běží znovu' : 'běh pokračuje' }}.
    </p>
    <p v-if="allowError" class="error" data-test="allow-error">{{ allowError }}</p>
    <p v-if="marked" class="done" data-test="mark-done-done">Task {{ run.task_id }} je hotový bez změn.</p>
    <p v-if="markError" class="error" data-test="mark-done-error">{{ markError }}</p>
    <p v-if="cancelled" class="done" data-test="cancel-done">Task {{ run.task_id }} je zrušený.</p>
    <p v-if="cancelError" class="error" data-test="cancel-error">{{ cancelError }}</p>
    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />
  </section>
</template>

<style scoped>
.failure-card {
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid rgba(255, 111, 103, 0.55);
  border-radius: 10px;
  background: rgba(255, 111, 103, 0.08);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

h3 {
  margin: 0;
  font-size: 17px;
  color: var(--red);
}

/* a blocked run waits for its blockers: not a failure */
.failure-card[data-kind='blocked'] {
  border-color: rgba(148, 163, 255, 0.55);
  background: rgba(148, 163, 255, 0.08);
}

.failure-card[data-kind='blocked'] h3 {
  color: var(--violet);
}

.actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.allow-writes,
.mark-done,
.cancel-task {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.allow-writes:disabled,
.mark-done:disabled,
.cancel-task:disabled {
  opacity: 0.6;
  cursor: default;
}

.sentence {
  margin: 8px 0 0;
}

.fact {
  margin-top: 10px;
}

h4 {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--faint);
  font-weight: normal;
}

ul {
  margin: 0;
  padding-left: 18px;
  font-size: 14px;
}

ul.mono {
  font-family: var(--mono);
  font-size: 13px;
}

li {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.full-error {
  margin-top: 10px;
  font-size: 13px;
}

.full-error pre {
  margin: 6px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: var(--mono);
}

.done {
  margin: 10px 0 0;
  color: var(--cyan);
}

.error {
  margin: 10px 0 0;
  color: var(--red);
}
</style>

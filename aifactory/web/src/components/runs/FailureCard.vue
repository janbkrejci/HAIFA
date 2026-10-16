<script setup lang="ts">
// The failure card at the top of a run detail: the kind of the failure in Czech, one
// sentence and the facts from the run's `failure_detail`, the whole error text, and the
// actions that exist for the kind (lib/failure.ts).
import { computed, ref } from 'vue'
import { Ban } from 'lucide-vue-next'
import { editTask } from '@/lib/backlog'
import { useConfirm } from '@/lib/confirm'
import { failureCard, type FailurePhase } from '@/lib/failure'
import { errorText } from '@/lib/format'
import { canRetry, type RunSummary } from '@/lib/runs'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'
import RetryRunButton from './RetryRunButton.vue'

const props = defineProps<{ run: RunSummary; phases?: readonly FailurePhase[] }>()
const emit = defineEmits<{ retried: []; cancelled: [] }>()

const card = computed(() => failureCard(props.run, props.phases ?? []))
const canContinue = computed(() => !!card.value?.actions.includes('continue') && canRetry(props.run))
const canCancel = computed(() => !!card.value?.actions.includes('cancel_task'))
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
        <RetryRunButton v-if="canContinue" :run-id="run.run_id" label="Pokračovat" @started="emit('retried')" />
        <button
          v-if="canCancel"
          type="button"
          class="cancel-task"
          data-test="cancel-task"
          :disabled="cancelling || cancelled"
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
        <li v-for="(item, i) in fact.items" :key="i" data-test="failure-item">{{ item }}</li>
      </ul>
    </div>
    <details v-if="fullError" class="full-error">
      <summary>Celá chybová zpráva</summary>
      <pre data-test="run-error">{{ fullError }}</pre>
    </details>
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

.actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.cancel-task {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

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

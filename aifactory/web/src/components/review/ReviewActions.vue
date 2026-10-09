<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { runHref } from '@/lib/router'
import type { ReviewAction, ReviewDetail } from '@/lib/review'
import { useConfirm } from '@/lib/confirm'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{
  detail: ReviewDetail
  busy: boolean
  /** The running action: its button shows the spinner. */
  pending?: ReviewAction | null
  /** Bumped by the parent after a return succeeded: the note is cleared. */
  returned?: number
}>()
const emit = defineEmits<{ approve: []; return: [note: string]; resolve: [] }>()

const note = ref('')
const running = computed(() => props.detail.running_run ?? null)
const blocked = computed(() => props.busy || running.value !== null)
const conflict = computed(() => props.detail.mergeability === 'conflict')
const actions = computed(() => props.detail.actions ?? { approve: false, return: false, resolve: false })

const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

async function onApprove() {
  const ok = await ask({
    title: `Schválit a mergovat PR ${props.detail.task_id} do ${props.detail.pr.base}?`,
    message: props.detail.approve_note,
  })
  if (ok) emit('approve')
}

async function onReturn() {
  const text = note.value.trim()
  if (!text) return
  const ok = await ask({
    title: `Vrátit PR ${props.detail.task_id} agentovi s poznámkou?`,
    message: text,
    confirmLabel: 'Vrátit',
  })
  if (ok) emit('return', text)
}

watch(
  () => props.returned,
  () => {
    note.value = ''
  },
)
</script>

<template>
  <div class="actions">
    <p v-if="running" class="info" data-test="running-info">
      Na PR běží běh
      <a :href="runHref(running.run_id)">{{ running.run_id }}</a>
      ({{ running.workflow ?? '—' }}); akce počkají, až doběhne.
    </p>

    <div v-if="conflict" class="conflict" data-test="conflict-banner">
      PR nejde mergovat do {{ detail.pr.base }} – „Vyřešit konflikt s base“ spustí workflow resolve (rebase +
      agent).
      <button
        type="button"
        class="btn primary"
        data-test="resolve"
        :disabled="blocked || !actions.resolve"
        :aria-busy="pending === 'resolve' || undefined"
        @click="emit('resolve')"
      >
        <Spinner v-if="pending === 'resolve'" />
        Vyřešit konflikt s base
      </button>
    </div>

    <div class="block">
      <button
        type="button"
        class="btn approve"
        data-test="approve"
        :disabled="blocked || !actions.approve"
        :aria-busy="pending === 'approve' || undefined"
        @click="onApprove"
      >
        <Spinner v-if="pending === 'approve'" />
        Schválit
      </button>
      <p class="note faint" data-test="ob3-note">{{ detail.approve_note }}</p>
    </div>

    <div class="block">
      <label for="return-note" class="label">Vrátit s poznámkou</label>
      <textarea
        id="return-note"
        v-model="note"
        data-test="return-note"
        rows="3"
        placeholder="Co má agent změnit…"
        :disabled="blocked || !actions.return"
      />
      <button
        type="button"
        class="btn"
        data-test="return"
        :disabled="blocked || !actions.return || !note.trim()"
        :aria-busy="pending === 'return' || undefined"
        @click="onReturn"
      >
        <Spinner v-if="pending === 'return'" />
        Vrátit
      </button>
    </div>

    <div v-if="!conflict && actions.resolve" class="block">
      <button
        type="button"
        class="btn subtle"
        data-test="resolve"
        :disabled="blocked"
        :aria-busy="pending === 'resolve' || undefined"
        @click="emit('resolve')"
      >
        <Spinner v-if="pending === 'resolve'" />
        Dorovnat s base
      </button>
    </div>

    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />
  </div>
</template>

<style scoped>
.actions {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.label {
  color: var(--dim);
}

textarea {
  width: 100%;
  max-width: 640px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.btn.approve {
  border-color: rgba(74, 222, 128, 0.55);
  color: var(--green);
}

.btn.primary {
  margin-left: 12px;
  border-color: var(--red);
  color: var(--red);
  font-weight: 700;
}

.btn.subtle {
  color: var(--dim);
}

.note {
  margin: 0;
  font-size: 14px;
}

.conflict {
  padding: 10px 14px;
  border: 1px solid rgba(255, 111, 103, 0.45);
  border-radius: 8px;
  background: rgba(255, 111, 103, 0.09);
  color: var(--red);
}

.info {
  margin: 0;
  color: var(--blue);
}
</style>

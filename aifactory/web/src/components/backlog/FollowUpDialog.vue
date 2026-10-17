<script setup lang="ts">
// Otevřít navazující task: a done task is never reopened; a new task follows it
// (`factory task follow-up`). The person says what to change, redo or finish, optionally a
// title, and whether the new task runs at once (default). Confirm creates the task and
// commits the backlog; with „Spustit hned“ the server commits it and starts the run, without
// it the dialog commits it (`factory backlog commit`).
import { computed, ref } from 'vue'
import { GitBranchPlus, X } from 'lucide-vue-next'
import { commitBacklog, flattenIssues, followUpTask, type FollowUpResult, type WriteError } from '@/lib/backlog'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'

const props = defineProps<{
  /** Id of the done task the new one follows. */
  taskId: string
  taskTitle: string
}>()
const emit = defineEmits<{ created: [result: FollowUpResult]; cancel: [] }>()

const body = ref('')
const title = ref('')
const runNow = ref(true)
const saving = ref(false)
const error = ref<WriteError | null>(null)
/** The task was written but its backlog commit failed: it is opened, never created twice. */
const uncommitted = ref<FollowUpResult | null>(null)

const canSubmit = computed(() => !saving.value && !uncommitted.value && body.value.trim() !== '')
const defaultTitle = computed(() => `Navazuje na ${props.taskId}: ${props.taskTitle}`)

async function submit() {
  if (!canSubmit.value) return
  error.value = null
  saving.value = true
  const run = runNow.value
  let result: FollowUpResult | null = null
  try {
    result = await followUpTask(props.taskId, {
      body: body.value.trim(),
      ...(title.value.trim() ? { title: title.value.trim() } : {}),
      run,
    })
    // with run the server has committed the backlog already
    if (!run) {
      result = { ...result, commit: await commitBacklog(`backlog: ${result.task.id} follows ${props.taskId}`) }
    }
    emit('created', result)
  } catch (e) {
    error.value = flattenIssues(e)
    if (result) uncommitted.value = result
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="follow-up-dialog" role="dialog" aria-labelledby="follow-up-title" data-test="follow-up-dialog">
    <div class="head">
      <h3 id="follow-up-title"><GitBranchPlus :size="16" aria-hidden="true" /> Navazující task na {{ taskId }}</h3>
      <button type="button" class="icon" aria-label="Zavřít" data-test="follow-up-close" :disabled="saving" @click="emit('cancel')">
        <X :size="16" />
      </button>
    </div>
    <fieldset class="fields" :disabled="saving">
      <label>
        Co změnit, předělat nebo dodělat
        <textarea v-model="body" data-test="follow-up-body" rows="5" />
      </label>
      <label>
        Titulek (volitelný)
        <input v-model="title" type="text" data-test="follow-up-title" :placeholder="defaultTitle" />
      </label>
      <label class="check">
        <input v-model="runNow" type="checkbox" data-test="follow-up-run" />
        Spustit hned
      </label>
    </fieldset>
    <IssueList v-if="error" :message="error.message" :issues="error.issues" />
    <div v-if="uncommitted" class="actions">
      <p data-test="follow-up-uncommitted">
        {{ uncommitted.task.id }} je zapsaný, ale backlog se nepodařilo commitnout. Commitni ho z banneru backlogu.
      </p>
      <button type="button" class="primary" data-test="follow-up-open" @click="emit('created', uncommitted)">
        Otevřít {{ uncommitted.task.id }}
      </button>
    </div>
    <div v-else class="actions">
      <button
        type="button"
        class="primary"
        data-test="follow-up-submit"
        :disabled="!canSubmit"
        :aria-busy="saving || undefined"
        @click="submit"
      >
        <Spinner v-if="saving" /> {{ runNow ? 'Založit a spustit' : 'Založit' }}
      </button>
      <button type="button" data-test="follow-up-cancel" :disabled="saving" @click="emit('cancel')">Zrušit</button>
    </div>
  </section>
</template>

<style scoped>
.follow-up-dialog {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid rgba(108, 182, 255, 0.45);
  border-radius: 10px;
  background: var(--panel-2);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h3 {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  color: var(--dim);
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  color: var(--dim);
}

label.check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

input[type='text'],
textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
}

textarea {
  resize: vertical;
  font-family: var(--mono);
  font-size: 14px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.actions p {
  margin: 0;
  flex-basis: 100%;
}

button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

button.icon {
  padding: 4px 6px;
}

button.primary {
  border-color: var(--blue);
  color: var(--blue);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>

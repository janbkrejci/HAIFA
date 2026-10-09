<script setup lang="ts">
// The form for a new project or step (`factory backlog add [PARENT] --id --title --body`).
import { computed, ref } from 'vue'
import { levelNoun, suggestContainerCode, type AddContainerInput, type WriteError } from '@/lib/backlog'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'

const props = defineProps<{
  /** The level of the new container (`project`, `step`). */
  level: string
  /** The project of a new step; null for a new project. */
  parent?: string | null
  /** Title of the parent, shown in the heading. */
  parentTitle?: string | null
  /** Codes of the containers beside the new one: the suggested code follows them. */
  siblings?: string[]
  busy: boolean
  /** The submit is running (spinner in Založit). */
  pending?: boolean
  error: WriteError | null
}>()

const emit = defineEmits<{
  submit: [input: AddContainerInput]
  cancel: []
}>()

const code = ref('')
const title = ref('')
const body = ref('')

const noun = computed(() => levelNoun(props.level))
const placeholder = computed(() => suggestContainerCode(props.level, props.parent ?? null, props.siblings ?? []))
const canSubmit = computed(() => !props.busy && !!code.value.trim() && !!title.value.trim())

function onSubmit() {
  if (!canSubmit.value) return
  const input: AddContainerInput = { id: code.value.trim(), title: title.value.trim() }
  if (props.parent) input.parent = props.parent
  if (body.value.trim()) input.body = body.value
  emit('submit', input)
}
</script>

<template>
  <form class="container-form" data-test="container-form" :data-level="level" @submit.prevent="onSubmit">
    <h2>
      Nový {{ noun }}
      <span v-if="parent" class="faint" data-test="container-parent">
        v <span class="mono">{{ parent }}</span><template v-if="parentTitle"> · {{ parentTitle }}</template>
      </span>
    </h2>

    <label>
      Kód
      <input
        v-model="code"
        data-test="container-id"
        type="text"
        required
        :placeholder="placeholder"
        autocomplete="off"
      />
      <span v-if="parent" class="hint faint">Kód začíná kódem <span class="mono">{{ parent }}-</span>.</span>
    </label>

    <label>
      Název
      <input v-model="title" data-test="container-title" type="text" required />
    </label>

    <label>
      Popis
      <textarea v-model="body" data-test="container-body-input" rows="6" placeholder="markdown" />
    </label>

    <div class="actions">
      <button
        type="submit"
        class="primary"
        data-test="container-save"
        :disabled="!canSubmit"
        :aria-busy="pending || undefined"
      >
        <Spinner v-if="pending" />
        Založit
      </button>
      <button type="button" data-test="container-cancel" @click="emit('cancel')">Zrušit</button>
    </div>

    <IssueList v-if="error" :message="error.message" :issues="error.issues" />
  </form>
</template>

<style scoped>
.container-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 720px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

h2 {
  margin: 0 0 4px;
  font-size: 18px;
}

h2 .faint {
  font-size: 15px;
  font-weight: 400;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--dim);
}

input[type='text'],
textarea {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
}

textarea {
  font-family: var(--mono);
  font-size: 14px;
}

.mono {
  font-family: var(--mono);
}

.hint {
  font-size: 13px;
}

.actions {
  display: flex;
  gap: 10px;
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

button.primary {
  border-color: var(--blue);
  color: var(--blue);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>

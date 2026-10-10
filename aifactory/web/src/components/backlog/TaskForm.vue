<script setup lang="ts">
// One form for a new task (factory task add) and for editing a task (factory task edit).
import { computed, ref } from 'vue'
import {
  INHERIT_LABEL,
  SETTING_LABELS,
  autoMode,
  levelLabel,
  levelNoun,
  splitIds,
  splitLines,
  type AddTaskInput,
  type EditTaskInput,
  type StepRef,
  type TaskNode,
  type WriteError,
} from '@/lib/backlog'
import type { SelectOption } from '@/lib/select'
import { useLevels } from '@/lib/names'
import { newStepHref } from '@/lib/router'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'
import { useHarnessChoices } from '@/lib/machineHarnesses'
import TaskAdvice, { type TaskProposal } from './TaskAdvice.vue'
import WorkflowAdvice, { type Recommendation } from './WorkflowAdvice.vue'

const props = defineProps<{
  mode: 'add' | 'edit'
  steps: StepRef[]
  workflows: string[]
  task?: TaskNode | null
  busy: boolean
  error: WriteError | null
  /** The submit is running (spinner in Založit/Uložit). */
  pending?: boolean
  taskBody?: string
  initialTitle?: string
  initialBody?: string
  /** The step a new task starts in (`#/r/<id>/backlog/new/<step id>`). */
  initialStep?: string | null
}>()

const emit = defineEmits<{
  submit: [input: AddTaskInput | EditTaskInput]
  cancel: []
}>()

const task = props.task ?? null
const initialStatus = task?.status ?? 'todo'
const initialWorkflow = task?.own_workflow ?? ''
const initialWrites = task?.own_writes ?? []
const initialInherit = initialWrites.length === 0
const initialAutoMerge = autoMode(task?.own_auto_merge)

const step = ref(
  props.steps.find((s) => s.id === props.initialStep)?.id ?? props.steps[0]?.id ?? '',
)
const title = ref(task?.title ?? props.initialTitle ?? '')
const taskId = ref('')
const workflow = ref(initialWorkflow)
const writesText = ref(initialWrites.join('\n'))
const inheritWrites = ref(initialInherit)
const dependsText = ref((task?.depends_on ?? []).join(', '))
const relatedText = ref((task?.related ?? []).join(', '))
const parameterBusy = ref(false)
const parameters = ref<Record<string, unknown> | undefined>()
const parameterFields = ['harness', 'model', 'thinking', 'source', 'target', 'test_timeout', 'specs_dir', 'docs_dir', 'auto_continue', 'auto_merge']
const { harnessOptions, modelOptions } = useHarnessChoices()
const projectHarness = computed(() => props.steps.find(s => s.id === step.value)?.harness ?? '')
/** A parameter's value: the typed or proposed one, else the task's own one (edit). */
function parameterValue(key: string): unknown {
  const typed = parameters.value
  if (typed && key in typed) return typed[key]
  return task?.own_parameters?.[key]
}
function parameterText(key: string): string {
  const value = parameterValue(key)
  if (value == null) return ''
  return String(value)
}
const parameterFlagOptions: SelectOption[] = [
  { value: '', label: INHERIT_LABEL },
  { value: 'true', label: 'Zapnuto' },
  { value: 'false', label: 'Vypnuto' },
]
function setParameter(key: string, event: Event) {
  setParameterText(key, (event.target as HTMLInputElement).value)
}
function setParameterText(key: string, text: string) {
  const value = !text ? null : key === 'test_timeout' ? Number(text) : ['auto_continue', 'auto_merge'].includes(key) ? text === 'true' : text
  parameters.value = { ...parameters.value, [key]: value }
  if (key === 'harness') parameters.value.model = null
  if (key === 'auto_merge') autoMerge.value = autoMode(value as boolean | null)
}
const body = ref(props.mode === 'edit' ? props.taskBody ?? '' : props.initialBody ?? '')
const status = ref<string>(initialStatus)
const autoMerge = ref<string>(initialAutoMerge)
const adviceBusy = ref(false)
const advice = ref<{ result: Recommendation; id: string } | null>(null)
// Analyze the live draft, including the current manual or suggested selection.
const adviceDraft = computed(() => ({
  ...(props.mode === 'add' ? { step: step.value } : {}),
  ...(parameters.value ? { parameters: parameters.value } : {}),
  body: body.value, depends_on: splitIds(dependsText.value), related: splitIds(relatedText.value),
  title: title.value.trim(),
  writes: props.mode === 'edit' ? (inheritWrites.value ? null : splitLines(writesText.value)) : (splitLines(writesText.value).length || !inheritWrites.value ? splitLines(writesText.value) : null),
  workflow: workflow.value || null,
}))
const parameterDraft = computed(() => ({
  ...adviceDraft.value,
  parameters: {
    ...(task?.own_parameters ?? {}),
    ...(parameters.value ?? {}),
    ...(props.mode === 'edit' ? { auto_merge: autoMerge.value === 'inherit' ? null : autoMerge.value === 'on' } : {}),
  },
}))
function applyParameters(result: TaskProposal) {
  parameters.value = result.parameters
  if (result.parameters && 'auto_merge' in result.parameters) autoMerge.value = autoMode(result.parameters.auto_merge as boolean | null)
  title.value = result.title
  body.value = result.body
  writesText.value = (result.writes ?? []).join('\n')
  inheritWrites.value = result.writes === null
  dependsText.value = result.depends_on.join(', ')
  relatedText.value = result.related.join(', ')
  workflow.value = result.workflow ?? ''
  advice.value = null
}
function applyAdvice(result: Recommendation, id: string) {
  advice.value = { result, id }
  workflow.value = result.workflow_name
}
function attachAdvice<T extends AddTaskInput | EditTaskInput>(input: T): T {
  if (advice.value && workflow.value === advice.value.result.workflow_name) {
    input.workflow = workflow.value
    input.workflow_advice_id = advice.value.id
  }
  return input
}


const isDone = computed(() => initialStatus === 'done')
const level = useLevels()
const stepLabel = computed(() => levelLabel(level.step.value))
const taskNoun = computed(() => levelNoun(level.task.value))
const taskGen = computed(() => levelNoun(level.task.value, 'gen'))

const stepOptions = computed<SelectOption[]>(() =>
  props.steps.map((s) => ({ value: s.id, label: s.title ? `${s.id} · ${s.title}` : s.id })),
)
const statusOptions = computed<SelectOption[]>(() => [
  ...(isDone.value ? [{ value: 'done', label: 'Hotovo' }] : []),
  { value: 'todo', label: 'K řešení' },
  { value: 'cancelled', label: 'Zrušeno' },
])
function inheritedMergeLabel(): string {
  // The inherited value is known only while the task has none of its own.
  if (!task || task.own_auto_merge != null) return INHERIT_LABEL
  return `${INHERIT_LABEL} (${task.effective_auto_merge ? 'zapnuto' : 'vypnuto'})`
}
const autoMergeOptions = computed<SelectOption[]>(() => [
  { value: 'inherit', label: inheritedMergeLabel() },
  { value: 'on', label: 'Zapnuto' },
  { value: 'off', label: 'Vypnuto' },
])
/** A new task needs a step; without one the form explains how to create it. */
const noSteps = computed(() => props.mode === 'add' && props.steps.length === 0)
const stepNoun = computed(() => levelNoun(level.step.value))
/** The task can no longer change (done, cancelled, running or in review). */
const frozen = computed(() => ['done', 'cancelled', 'running', 'in review'].includes(task?.board_state ?? ''))
/** Why the AI proposals are disabled; '' when they can run. */
const adviceBlocker = computed(() => {
  if (frozen.value) return `${levelLabel(level.task.value)} už nejde měnit.`
  if (props.mode === 'add' && !step.value) return `Vyber ${stepNoun.value}.`
  if (!title.value.trim()) return 'Vyplň titulek.'
  return ''
})
const visibleParameters = computed(() =>
  parameterFields.filter((key) => props.mode === 'add' || key !== 'auto_merge'),
)
const workflowOptions = computed<SelectOption[]>(() => [
  { value: '', label: 'Zděděno' },
  ...Array.from(new Set([...props.workflows, ...(advice.value ? [advice.value.result.workflow_name] : [])])).map((w) => ({ value: w, label: w })),
])

function addInput(): AddTaskInput {
  const input: AddTaskInput = { step: step.value, title: title.value.trim() }
  const id = taskId.value.trim()
  if (id) input.id = id
  if (workflow.value) input.workflow = workflow.value
  const writes = splitLines(writesText.value)
  if (writes.length || !inheritWrites.value) input.writes = writes
  const depends = splitIds(dependsText.value)
  if (depends.length) input.depends_on = depends
  const related = splitIds(relatedText.value)
  if (related.length) input.related = related
  if (body.value.trim()) input.body = body.value
  if (parameters.value) input.parameters = parameters.value
  return attachAdvice(input)
}

function sameList(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i])
}

const editInput = computed<EditTaskInput>(() => {
  const input: EditTaskInput = {}
  if (!task) return input
  if (parameters.value) input.parameters = { ...parameters.value, auto_merge: autoMerge.value === 'inherit' ? null : autoMerge.value === 'on' }
  if (body.value !== (props.taskBody ?? '')) input.body = body.value
  if (!sameList(splitIds(dependsText.value), task.depends_on ?? [])) input.depends_on = splitIds(dependsText.value)
  if (!sameList(splitIds(relatedText.value), task.related ?? [])) input.related = splitIds(relatedText.value)
  if (title.value.trim() !== task.title) input.title = title.value.trim()
  if (!isDone.value && status.value !== initialStatus) {
    input.status = status.value as 'todo' | 'cancelled'
  }
  if (workflow.value !== initialWorkflow) {
    if (workflow.value) input.workflow = workflow.value
    else input.clear_workflow = true
  }
  if (inheritWrites.value) {
    if (!initialInherit) input.clear_writes = true
  } else {
    const writes = splitLines(writesText.value)
    if (initialInherit || !sameList(writes, initialWrites)) input.writes = writes
  }
  if (autoMerge.value !== initialAutoMerge) {
    if (autoMerge.value === 'inherit') input.clear_auto_merge = true
    else input.auto_merge = autoMerge.value === 'on'
  }
  return attachAdvice(input)
})

const canSubmit = computed(() => {
  if (props.busy || adviceBusy.value || parameterBusy.value) return false
  if (props.mode === 'add') return Boolean(step.value && title.value.trim())
  return Object.keys(editInput.value).length > 0
})

function onSubmit() {
  if (!canSubmit.value) return
  emit('submit', props.mode === 'add' ? addInput() : editInput.value)
}
</script>

<template>
  <form class="task-form" :data-mode="mode" @submit.prevent="onSubmit">
    <h2 v-if="mode === 'add'">Nový {{ taskNoun }}</h2>
    <h2 v-else>
      Upravit {{ task?.id ?? '' }}
    </h2>

    <p v-if="noSteps" class="no-steps" data-test="no-steps">
      {{ levelLabel(level.task.value) }} patří do {{ levelNoun(level.step.value, 'gen') }}, zatím žádný není.
      <a :href="newStepHref()" data-test="no-steps-link">Založit {{ stepNoun }}</a>
    </p>
    <label v-else-if="mode === 'add'">
      {{ stepLabel }}
      <SelectMenu v-model="step" data-test="step" :label="stepLabel" :options="stepOptions" />
    </label>

    <label>
      Titulek
      <input v-model="title" data-test="title" type="text" required />
    </label>

    <label v-if="mode === 'add'">
      Id
      <input v-model="taskId" data-test="id" type="text" placeholder="další volné" />
    </label>

    <label v-if="mode === 'edit'">
      Status
      <SelectMenu
        v-model="status"
        data-test="status"
        label="Status"
        :options="statusOptions"
        :disabled="isDone"
      />
      <span v-if="isDone" class="hint faint" data-test="done-note">
        Hotový {{ taskNoun }} mění jen schválení PR.
      </span>
    </label>

    <label>
      Workflow
      <SelectMenu v-model="workflow" data-test="workflow" label="Workflow" :options="workflowOptions" />
    </label>

    <label>
      Zadání
      <textarea v-model="body" data-test="body" rows="6" />
    </label>

    <p v-if="adviceBlocker" class="hint faint" data-test="advice-blocker">
      Návrhy agenta: {{ adviceBlocker }}
    </p>

    <TaskAdvice
      :draft="parameterDraft"
      :task-id="task?.id"
      :disabled="busy || adviceBusy || !!adviceBlocker"
      @busy="parameterBusy = $event"
      @result="applyParameters"
    />

    <WorkflowAdvice
      :draft="adviceDraft"
      :task-id="task?.id"
      :disabled="busy || parameterBusy || !!adviceBlocker"
      @busy="adviceBusy = $event"
      @result="applyAdvice"
      @invalidate="advice = null"
    />

    <label v-if="mode === 'edit'">
      Auto-merge
      <SelectMenu
        v-model="autoMerge"
        data-test="auto-merge"
        label="Auto-merge"
        :options="autoMergeOptions"
      />
      <span class="hint faint">Vypni u {{ taskGen }}, který mění hlídač nebo oprávnění.</span>
    </label>

    <label>
      Writes
      <textarea
        v-model="writesText"
        data-test="writes"
        rows="3"
        placeholder="jedna cesta na řádek"
        :disabled="mode === 'edit' && inheritWrites"
      />
    </label>
    <label v-if="mode === 'edit'" class="check">
      <input v-model="inheritWrites" data-test="inherit-writes" type="checkbox" />
      dědit writes
    </label>

    <div class="relationships">
      <label>
        Závisí na
        <input v-model="dependsText" data-test="depends" type="text" placeholder="M01-S01-T01, …" />
      </label>
      <label>
        Související
        <input v-model="relatedText" data-test="related" type="text" placeholder="M01-S01-T01, …" />
      </label>
    </div>

    <details data-test="task-parameters" :open="!!parameters">
      <summary>Další parametry (prázdné = zděděno)</summary>
      <label v-for="key in visibleParameters" :key="key" :data-parameter="key">
        <span>{{ SETTING_LABELS[key] ?? key }} <code class="key">{{ key }}</code></span>
        <SelectMenu
          v-if="key === 'harness'" :model-value="parameterText(key)" :options="harnessOptions" label="Harness tasku" :data-test="`parameter-${key}`" @update:model-value="setParameterText(key, $event)" />
        <SelectMenu v-else-if="key === 'model'" :model-value="parameterText(key)" :options="modelOptions(parameterText('harness') || projectHarness)" label="Model tasku" :data-test="`parameter-${key}`" @update:model-value="setParameterText(key, $event)" />
        <SelectMenu
          v-else-if="['auto_continue', 'auto_merge'].includes(key)"
          :model-value="parameterText(key)"
          :data-test="`parameter-${key}`"
          :label="SETTING_LABELS[key] ?? key"
          :options="parameterFlagOptions"
          @update:model-value="setParameterText(key, $event)"
        />
        <input
          v-else
          :data-test="`parameter-${key}`"
          :type="key === 'test_timeout' ? 'number' : 'text'"
          :value="parameterText(key)"
          @input="setParameter(key, $event)"
        />
      </label>
    </details>

    <div class="actions">
      <button
        type="submit"
        class="primary"
        data-test="save"
        :disabled="!canSubmit"
        :aria-busy="pending || undefined"
      >
        <Spinner v-if="pending" />
        {{ mode === 'add' ? 'Založit' : 'Uložit' }}
      </button>
      <button type="button" data-test="cancel" @click="emit('cancel')">Zrušit</button>
    </div>

    <IssueList v-if="error" :message="error.message" :issues="error.issues" />
  </form>
</template>

<style scoped>
.task-form {
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

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--dim);
}

label.check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
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

.hint {
  font-size: 13px;
}

.no-steps {
  margin: 0;
  color: var(--amber);
}

code.key {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--faint);
}

summary {
  cursor: pointer;
  color: var(--dim);
}

details[data-test='task-parameters'] {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

details[data-test='task-parameters'] > label {
  margin-top: 8px;
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

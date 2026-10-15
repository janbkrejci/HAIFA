<script setup lang="ts">
// One form for a new task (factory task add) and for editing a task (factory task edit).
import { computed, nextTick, ref, watch } from 'vue'
import {
  CODE_RE,
  INHERIT_LABEL,
  SETTING_LABELS,
  THINKING_LEVELS,
  autoMode,
  levelLabel,
  levelNoun,
  splitLines,
  shortCode,
  suggestTaskCode,
  type AddTaskInput,
  type EditTaskInput,
  type StepRef,
  type TaskNode,
  type WriteError,
} from '@/lib/backlog'
import type { SelectOption } from '@/lib/select'
import { useLevels, useNames } from '@/lib/names'
import { newStepHref } from '@/lib/router'
import { askDiscard, useUnsavedGuard } from '@/lib/leaveGuard'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import IdPicker from './IdPicker.vue'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'
import { useHarnessChoices } from '@/lib/machineHarnesses'
import ImproveButton, { type TaskProposal } from './ImproveButton.vue'
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
  /** Ids of the existing tasks: the suggested code of a new task follows them. */
  taskIds?: string[]
  /** Start "Vylepšit agentem" right away (the detail's improve button opened the form). */
  autoImprove?: boolean
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
/** The short code of a new task (`T05`); empty means the next free one. */
const taskCode = computed(() => shortCode(step.value || null, taskId.value))
const taskCodeValid = computed(() => !taskCode.value || CODE_RE.test(taskCode.value))
const nextTaskCode = computed(() => (step.value ? suggestTaskCode(step.value, props.taskIds ?? []) : 'T01'))
const taskIdPreview = computed(() => (step.value ? `${step.value}-${taskCode.value || nextTaskCode.value}` : ''))
const workflow = ref(initialWorkflow)
const writesText = ref(initialWrites.join('\n'))
const inheritWrites = ref(initialInherit)
const depends = ref<string[]>([...(task?.depends_on ?? [])])
const related = ref<string[]>([...(task?.related ?? [])])
const parameterBusy = ref(false)
const parameters = ref<Record<string, unknown> | undefined>()
const parameterFields = ['harness', 'model', 'thinking', 'test_timeout', 'auto_continue', 'auto_merge']
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
const thinkingOptions: SelectOption[] = [
  { value: '', label: INHERIT_LABEL },
  ...THINKING_LEVELS.map((level) => ({ value: level, label: level })),
]
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
  body: body.value, depends_on: depends.value, related: related.value,
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
/** "Další nastavení" opens when the task uses any of them (edit) or the agent changed one. */
function hasOwnParameters(values: Record<string, unknown> | null | undefined): boolean {
  return Object.values(values ?? {}).some((v) => v != null && v !== '')
}
const advancedOpen = ref(
  props.mode === 'edit' && !!task && (
    initialStatus !== 'todo' || task.own_auto_merge != null || initialWrites.length > 0
    || (task.depends_on ?? []).length > 0 || (task.related ?? []).length > 0
    || hasOwnParameters(task.own_parameters)
  ),
)
const workflowAdvice = ref<InstanceType<typeof WorkflowAdvice> | null>(null)
/** Apply the improved task, then propose its workflow from the improved draft (same advice as the button). */
async function applyParameters(result: TaskProposal) {
  const before = JSON.stringify([writesText.value, inheritWrites.value, depends.value, related.value, autoMerge.value])
  parameters.value = result.parameters
  if (result.parameters && 'auto_merge' in result.parameters) autoMerge.value = autoMode(result.parameters.auto_merge as boolean | null)
  title.value = result.title
  body.value = result.body
  writesText.value = (result.writes ?? []).join('\n')
  inheritWrites.value = result.writes === null
  depends.value = [...result.depends_on]
  related.value = [...result.related]
  workflow.value = result.workflow ?? ''
  advice.value = null
  const after = JSON.stringify([writesText.value, inheritWrites.value, depends.value, related.value, autoMerge.value])
  if (before !== after || hasOwnParameters(result.parameters)) advancedOpen.value = true
  // Let the advice see the improved draft (its watcher drops the old result first).
  await nextTick()
  await workflowAdvice.value?.start()
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
/** The task can no longer change (done, cancelled, running, in review or awaiting merge). */
const frozen = computed(() =>
  ['done', 'cancelled', 'running', 'in review', 'awaiting merge'].includes(task?.board_state ?? ''),
)
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
const { names } = useNames()
/** Codes of the backlog to link to, `<id> · <title>`; the task itself is left out. */
/** Both links may point to a task, a step or a project. */
const codeOptions = computed<SelectOption[]>(() =>
  Object.entries(names.value)
    .filter(([id]) => id !== task?.id)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([id, n]) => ({ value: id, label: n.title ? `${id} · ${n.title}` : id })),
)
const workflowOptions = computed<SelectOption[]>(() => [
  { value: '', label: 'Zděděno' },
  ...Array.from(new Set([...props.workflows, ...(advice.value ? [advice.value.result.workflow_name] : [])])).map((w) => ({ value: w, label: w })),
])

function addInput(): AddTaskInput {
  const input: AddTaskInput = { step: step.value, title: title.value.trim() }
  if (taskCode.value) input.id = taskCode.value
  if (workflow.value) input.workflow = workflow.value
  const writes = splitLines(writesText.value)
  if (writes.length || !inheritWrites.value) input.writes = writes
  if (depends.value.length) input.depends_on = [...depends.value]
  if (related.value.length) input.related = [...related.value]
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
  if (!sameList(depends.value, task.depends_on ?? [])) input.depends_on = [...depends.value]
  if (!sameList(related.value, task.related ?? [])) input.related = [...related.value]
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
  if (props.mode === 'add') return Boolean(step.value && title.value.trim() && taskCodeValid.value)
  return Object.keys(editInput.value).length > 0
})

/** Everything the user can change, to tell an edited form from the opened one. */
function formState(): string {
  return JSON.stringify([
    step.value, title.value, taskId.value, workflow.value, writesText.value, inheritWrites.value,
    depends.value, related.value, parameters.value ?? null, body.value, status.value, autoMerge.value,
  ])
}
const pristine = formState()
/** Submitted (or discarded): leaving after the save must not ask. A failed write makes it dirty again. */
const settled = ref(false)
const dirty = computed(() => !settled.value && formState() !== pristine)
useUnsavedGuard(() => dirty.value)
watch(
  () => props.error,
  (error) => {
    if (error) settled.value = false
  },
)

function onSubmit() {
  if (!canSubmit.value) return
  settled.value = true
  emit('submit', props.mode === 'add' ? addInput() : editInput.value)
}

/** Zrušit drops the changes only after the user agrees. */
async function onCancel() {
  if (dirty.value) {
    if (!(await askDiscard())) return
    settled.value = true
  }
  emit('cancel')
}
</script>

<template>
  <form class="task-form" :data-mode="mode" @submit.prevent="onSubmit">
    <div class="form-head">
      <h2 v-if="mode === 'add'">Nový {{ taskNoun }}</h2>
      <h2 v-else>Upravit {{ task?.id ?? '' }}</h2>
      <ImproveButton
        v-if="!noSteps"
        :draft="parameterDraft"
        :task-id="task?.id"
        :disabled="busy || adviceBusy"
        :blocker="adviceBlocker"
        :autostart="autoImprove"
        @busy="parameterBusy = $event"
        @result="applyParameters"
      />
    </div>

    <p v-if="noSteps" class="no-steps" data-test="no-steps">
      {{ levelLabel(level.task.value) }} patří do {{ levelNoun(level.step.value, 'gen') }}, zatím žádný není.
      <a :href="newStepHref()" data-test="no-steps-link">Založit {{ stepNoun }}</a>
    </p>

    <fieldset class="fields" :disabled="parameterBusy" data-test="fields">
      <div v-if="mode === 'add' && !noSteps" class="pair">
        <label>
          {{ stepLabel }}
          <SelectMenu v-model="step" data-test="step" :label="stepLabel" :options="stepOptions" />
        </label>
        <label>
          Kód (volitelné)
          <input v-model="taskId" data-test="id" type="text" :placeholder="nextTaskCode" autocomplete="off" />
          <span v-if="!taskCodeValid" class="hint error" data-test="id-invalid">Kód smí obsahovat jen písmena, číslice, „.“ a „_“.</span>
          <span v-else-if="taskIdPreview" class="hint faint" data-test="id-preview">Id: <span class="mono">{{ taskIdPreview }}</span></span>
        </label>
      </div>

      <label>
        Titulek
        <input v-model="title" data-test="title" type="text" required />
      </label>

      <label>
        Zadání
        <textarea v-model="body" data-test="body" rows="14" />
      </label>

      <div class="workflow-row">
        <label class="workflow-field">
          Workflow
          <SelectMenu v-model="workflow" data-test="workflow" label="Workflow" :options="workflowOptions" />
        </label>

        <WorkflowAdvice
        ref="workflowAdvice"
        class="workflow-advice"
        :draft="adviceDraft"
        :task-id="task?.id"
        :disabled="busy || parameterBusy || !!adviceBlocker"
        @busy="adviceBusy = $event"
        @result="applyAdvice"
        @invalidate="advice = null"
        />
      </div>

      <details data-test="advanced" :open="advancedOpen" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
        <summary>Další nastavení</summary>
        <div class="advanced">
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

          <div class="pair">
            <div class="field">
              <span>Závisí na</span>
              <IdPicker v-model="depends" data-test="depends" label="Závisí na" :options="codeOptions" :dialog="mode === 'edit'" />
            </div>
            <div class="field">
              <span>Související</span>
              <IdPicker v-model="related" data-test="related" label="Související" :options="codeOptions" />
            </div>
          </div>

          <div class="parameters" data-test="task-parameters">
            <h4>Parametry (prázdné = zděděno)</h4>
            <label v-for="key in visibleParameters" :key="key" :data-parameter="key">
              <span class="parameter-name">
                {{ SETTING_LABELS[key] ?? key }} <code class="key">{{ key }}</code>
              </span>
              <SelectMenu
                v-if="key === 'harness'" :model-value="parameterText(key)" :options="harnessOptions" label="Harness tasku" :data-test="`parameter-${key}`" @update:model-value="setParameterText(key, $event)" />
              <SelectMenu v-else-if="key === 'model'" :model-value="parameterText(key)" :options="modelOptions(parameterText('harness') || projectHarness)" label="Model tasku" :data-test="`parameter-${key}`" @update:model-value="setParameterText(key, $event)" />
              <SelectMenu v-else-if="key === 'thinking'" :model-value="parameterText(key)" :options="thinkingOptions" :label="SETTING_LABELS[key] ?? key" :data-test="`parameter-${key}`" @update:model-value="setParameterText(key, $event)" />
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
          </div>
        </div>
      </details>
    </fieldset>

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
      <button type="button" data-test="cancel" @click="onCancel">Zrušit</button>
    </div>

    <IssueList v-if="error" :message="error.message" :issues="error.issues" />
  </form>
</template>

<style scoped>
.task-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 900px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

h2 {
  margin: 0;
  font-size: 18px;
}

.form-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.advanced,
.parameters {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.advanced {
  margin-top: 12px;
}

h4 {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--faint);
}

label,
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  color: var(--dim);
}

.workflow-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 12px;
}

.workflow-field {
  flex: 0 1 320px;
}

/* the button sits beside the select, under the label's line */
.workflow-row .workflow-advice {
  flex: 1 1 240px;
  margin-top: 26px;
}

.parameter-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

label.check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

input[type='text'],
input[type='number'],
textarea {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
}

textarea {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  resize: vertical;
  overflow-wrap: anywhere;
  font-family: var(--mono);
  font-size: 14px;
}

.hint {
  font-size: 13px;
}

.mono {
  font-family: var(--mono);
}

.hint.error {
  color: var(--red);
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

<script setup lang="ts">
// Nový záměr: the person writes an intent and chooses a project (a new step) or a step (new
// tasks); the proposer agent proposes the tasks (`web.intent`). Its progress is shown while
// it works; the result is a tree of the new tasks with expandable texts and the findings of
// the quality check. A task can be removed or its text edited, Upřesni sends a note to the
// same agent session, Použít writes the proposal and commits the backlog.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Lightbulb, Pencil, Undo2, X } from 'lucide-vue-next'
import {
  applyIntent,
  discardIntent,
  fetchIntent,
  isWorking,
  parseTarget,
  refineIntent,
  startIntent,
  type IntentJob,
  type Proposal,
  type ProposalFinding,
  type TaskEdit,
} from '@/lib/intent'
import { flattenIssues, levelLabel, levelNoun, type ScopeOption, type StepRef, type WriteError } from '@/lib/backlog'
import { useLevels } from '@/lib/names'
import { currentRepoId } from '@/lib/router'
import type { SelectOption } from '@/lib/select'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'

const props = withDefaults(
  defineProps<{
    projects: ScopeOption[]
    steps: StepRef[]
    /** Projects get a new step (false when the top level holds tasks only). */
    allowProjects?: boolean
    /** A project or step id to preselect. */
    initial?: string | null
    /** Milliseconds between two reads of a running proposal. */
    pollMs?: number
  }>(),
  { allowProjects: true, initial: null, pollMs: 700 },
)
const emit = defineEmits<{ applied: [proposal: Proposal]; cancel: [] }>()

const level = useLevels()
const intent = ref('')
const target = ref('')
const job = ref<IntentJob | null>(null)
const error = ref<WriteError | null>(null)
const note = ref('')
const applying = ref(false)
const sending = ref(false)
/** Edited title and body of each task of the shown proposal, by code. */
const edits = ref<Record<string, { title: string; body: string }>>({})
const removed = ref<Set<string>>(new Set())
const editing = ref<Set<string>>(new Set())

const targetOptions = computed<SelectOption[]>(() => [
  ...(props.allowProjects
    ? props.projects.map((p) => ({
        value: `project:${p.id}`,
        label: `${p.id}${p.title ? ` – ${p.title}` : ''} · nový ${levelNoun(level.step.value)}`,
      }))
    : []),
  ...props.steps.map((s) => ({
    value: `step:${s.id}`,
    label: `${s.id}${s.title ? ` – ${s.title}` : ''} · nové ${levelNoun(level.task.value)}y`,
  })),
])

watch(
  () => [props.initial, targetOptions.value.length] as const,
  () => {
    if (target.value || !props.initial) return
    const value = [`step:${props.initial}`, `project:${props.initial}`].find((v) =>
      targetOptions.value.some((o) => o.value === v),
    )
    if (value) target.value = value
  },
  { immediate: true },
)

const working = computed(() => isWorking(job.value?.state))
const proposal = computed(() => job.value?.proposal ?? null)
const ready = computed(() => job.value?.state === 'ready' && proposal.value !== null)
const busy = computed(() => working.value || applying.value || sending.value)
const canPropose = computed(() => !busy.value && intent.value.trim() !== '' && parseTarget(target.value) !== null)
const kept = computed<TaskEdit[]>(() =>
  (proposal.value?.tasks ?? [])
    .filter((t) => !removed.value.has(t.code))
    .map((t) => ({ code: t.code, title: edits.value[t.code]?.title ?? t.title, body: edits.value[t.code]?.body ?? t.body })),
)
const findings = computed<ProposalFinding[]>(() => proposal.value?.findings ?? [])
function taskFindings(id: string): ProposalFinding[] {
  return findings.value.filter((f) => f.task === id)
}
const otherFindings = computed(() => {
  const ids = new Set((proposal.value?.tasks ?? []).map((t) => t.id))
  return findings.value.filter((f) => !ids.has(f.task))
})

function resetEdits(next: Proposal | null) {
  edits.value = Object.fromEntries((next?.tasks ?? []).map((t) => [t.code, { title: t.title, body: t.body }]))
  removed.value = new Set()
  editing.value = new Set()
}

// ── polling ──────────────────────────────────────────────────────────────────
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
const scope = currentRepoId()

function stopPolling() {
  generation++
  clearTimeout(timer)
}

function show(next: IntentJob) {
  const round = job.value?.job_id === next.job_id ? job.value.round : null
  const wasWorking = isWorking(job.value?.state)
  job.value = next
  if (next.state === 'ready' && (wasWorking || round !== next.round)) resetEdits(next.proposal)
}

function poll(id: string) {
  const token = generation
  timer = setTimeout(async () => {
    if (token !== generation || scope !== currentRepoId()) return
    try {
      const next = await fetchIntent(id)
      if (token !== generation) return
      show(next)
      if (isWorking(next.state)) poll(id)
    } catch (e) {
      if (token === generation) error.value = flattenIssues(e)
    }
  }, props.pollMs)
}

async function propose() {
  const where = parseTarget(target.value)
  if (!canPropose.value || !where) return
  stopPolling()
  error.value = null
  const previous = job.value
  sending.value = true
  try {
    if (previous && previous.state !== 'applied') void discardIntent(previous.job_id).catch(() => undefined)
    job.value = null
    resetEdits(null)
    const started = await startIntent(intent.value.trim(), where)
    show(started)
    poll(started.job_id)
  } catch (e) {
    error.value = flattenIssues(e)
  } finally {
    sending.value = false
  }
}

async function refine() {
  const current = job.value
  if (!current || !ready.value || !note.value.trim() || busy.value) return
  error.value = null
  sending.value = true
  try {
    const next = await refineIntent(current.job_id, note.value.trim(), kept.value)
    note.value = ''
    show(next)
    poll(next.job_id)
  } catch (e) {
    error.value = flattenIssues(e)
  } finally {
    sending.value = false
  }
}

async function apply() {
  const current = job.value
  if (!current || !ready.value || busy.value || kept.value.length === 0) return
  error.value = null
  applying.value = true
  try {
    const result = await applyIntent(current.job_id, kept.value)
    job.value = { ...current, state: 'applied', proposal: result }
    emit('applied', result)
  } catch (e) {
    error.value = flattenIssues(e)
  } finally {
    applying.value = false
  }
}

function cancel() {
  stopPolling()
  const current = job.value
  if (current && current.state !== 'applied') void discardIntent(current.job_id).catch(() => undefined)
  job.value = null
  emit('cancel')
}

onBeforeUnmount(() => {
  stopPolling()
  const current = job.value
  if (current && current.state !== 'applied') void discardIntent(current.job_id).catch(() => undefined)
})

// ── task edits ───────────────────────────────────────────────────────────────
function toggle(set: Set<string>, code: string): Set<string> {
  const next = new Set(set)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  return next
}
function onRemove(code: string) {
  removed.value = toggle(removed.value, code)
  editing.value = new Set([...editing.value].filter((c) => c !== code))
}
function onEdit(code: string) {
  editing.value = toggle(editing.value, code)
}

const stepLabel = computed(() => levelLabel(level.step.value))
const taskNounPlural = computed(() => `${levelNoun(level.task.value)}y`)
const stateText = computed(() => {
  const j = job.value
  if (!j) return ''
  if (j.state === 'queued') return 'Návrh čeká na agenta…'
  return j.round > 1 ? `Agent upravuje návrh (kolo ${j.round})…` : 'Agent navrhuje…'
})
const appliedProposal = computed(() => (job.value?.state === 'applied' ? job.value.proposal : null))
const jobError = computed<WriteError | null>(() =>
  job.value?.error ? { message: job.value.error, issues: job.value.issues ?? [] } : null,
)
</script>

<template>
  <section class="intent-dialog" role="dialog" aria-labelledby="intent-title" data-test="intent-dialog">
    <div class="head">
      <h2 id="intent-title"><Lightbulb :size="18" aria-hidden="true" /> Nový záměr</h2>
      <button type="button" class="icon" aria-label="Zavřít" data-test="intent-close" @click="cancel">
        <X :size="16" />
      </button>
    </div>

    <fieldset class="fields" :disabled="busy || !!appliedProposal">
      <label>
        Záměr
        <textarea
          v-model="intent"
          data-test="intent-text"
          rows="3"
          placeholder="Co má nový kus práce přinést, jednou nebo pár větami."
        />
      </label>
      <label>
        Kam
        <SelectMenu
          v-model="target"
          data-test="intent-target"
          label="Kam"
          :options="targetOptions"
          :placeholder="`Vyber ${levelNoun(level.top.value)} nebo ${levelNoun(level.step.value)}`"
        />
      </label>
    </fieldset>
    <div class="actions">
      <button
        type="button"
        class="primary"
        data-test="intent-propose"
        :disabled="!canPropose || !!appliedProposal"
        @click="propose"
      >
        <Spinner v-if="sending && !job" />
        {{ job && !appliedProposal ? 'Navrhnout znovu' : 'Navrhnout' }}
      </button>
    </div>

    <div v-if="working" class="progress" data-test="intent-progress" aria-live="polite">
      <p class="state"><Spinner /> {{ stateText }}</p>
      <ol v-if="job?.progress.length">
        <li v-for="(item, n) in job.progress" :key="n" :data-kind="item.kind">{{ item.text }}</li>
      </ol>
    </div>

    <IssueList v-if="error" :message="error.message" :issues="error.issues" />
    <IssueList v-if="jobError && !working" :message="jobError.message" :issues="jobError.issues" />

    <div v-if="appliedProposal" class="applied" data-test="intent-applied">
      <p>
        Zapsáno: {{ appliedProposal.tasks.length }} {{ taskNounPlural }} v
        <span class="mono">{{ appliedProposal.step.id }}</span>.
        <template v-if="appliedProposal.commit?.committed">
          Backlog je commitnutý do {{ appliedProposal.commit.base }}.
        </template>
      </p>
      <p v-for="warning in appliedProposal.warnings ?? []" :key="warning" class="warning">{{ warning }}</p>
    </div>

    <div v-else-if="proposal && !working" class="result" data-test="intent-result">
      <p v-if="proposal.summary" class="summary">{{ proposal.summary }}</p>
      <div class="step" data-test="intent-step">
        <span class="level">{{ stepLabel }}</span>
        <span class="mono">{{ proposal.step.id }}</span>
        <strong>{{ proposal.step.title }}</strong>
        <span class="faint">{{ proposal.step.new ? 'nový' : 'existující' }}</span>
      </div>
      <MarkdownView v-if="proposal.step.new && proposal.step.body" :source="proposal.step.body" preview-only />

      <ul class="tasks">
        <li
          v-for="task in proposal.tasks"
          :key="task.code"
          :class="{ removed: removed.has(task.code) }"
          :data-task="task.id"
          data-test="intent-task"
        >
          <details :open="editing.has(task.code) || undefined">
            <summary>
              <span class="mono">{{ task.id }}</span>
              <span class="title">{{ edits[task.code]?.title ?? task.title }}</span>
              <span v-if="taskFindings(task.id).length" class="finding-count" data-test="intent-task-findings">
                {{ taskFindings(task.id).length }} nález
              </span>
            </summary>
            <dl class="meta">
              <dt>workflow</dt><dd>{{ task.workflow }}</dd>
              <dt>writes</dt><dd class="mono">{{ task.writes.join(', ') || '–' }}</dd>
              <dt>závisí na</dt><dd class="mono">{{ task.depends_on.join(', ') || '–' }}</dd>
            </dl>
            <ul v-if="taskFindings(task.id).length" class="findings">
              <li v-for="(f, n) in taskFindings(task.id)" :key="n" :data-rule="f.rule">
                <code>{{ f.rule }}</code>: {{ f.message }}
              </li>
            </ul>
            <div v-if="editing.has(task.code) && edits[task.code]" class="edit">
              <label>
                Titulek
                <input v-model="edits[task.code]!.title" type="text" data-test="intent-task-title" />
              </label>
              <label>
                Zadání
                <textarea v-model="edits[task.code]!.body" rows="10" data-test="intent-task-body" />
              </label>
            </div>
            <MarkdownView v-else :source="edits[task.code]?.body ?? task.body" preview-only />
          </details>
          <div class="task-actions">
            <button
              v-if="!removed.has(task.code)"
              type="button"
              data-test="intent-task-edit"
              :disabled="busy"
              @click="onEdit(task.code)"
            >
              <Pencil :size="14" /> {{ editing.has(task.code) ? 'Hotovo' : 'Upravit' }}
            </button>
            <button type="button" data-test="intent-task-remove" :disabled="busy" @click="onRemove(task.code)">
              <template v-if="removed.has(task.code)"><Undo2 :size="14" /> Vrátit</template>
              <template v-else><X :size="14" /> Odebrat</template>
            </button>
          </div>
        </li>
      </ul>

      <div v-if="otherFindings.length" class="findings" data-test="intent-findings">
        <h3>Nálezy kontroly</h3>
        <ul>
          <li v-for="(f, n) in otherFindings" :key="n" :data-rule="f.rule">
            <span class="mono">{{ f.task }}</span> <code>{{ f.rule }}</code>: {{ f.message }}
          </li>
        </ul>
      </div>
      <p v-if="findings.length" class="faint" data-test="intent-findings-count">
        Kontrola kvality: {{ findings.length }} nález(ů), návrh jde přesto použít.
      </p>

      <label class="refine">
        Upřesni
        <textarea
          v-model="note"
          data-test="intent-note"
          rows="2"
          :disabled="busy"
          placeholder="Připomínka k návrhu; agent ho upraví ve stejné session."
        />
      </label>
      <div class="actions">
        <button
          type="button"
          data-test="intent-refine"
          :disabled="busy || !ready || !note.trim()"
          @click="refine"
        >
          <Spinner v-if="sending" /> Upřesnit
        </button>
        <button
          type="button"
          class="primary"
          data-test="intent-apply"
          :disabled="busy || !ready || kept.length === 0"
          @click="apply"
        >
          <Spinner v-if="applying" /> Použít ({{ kept.length }})
        </button>
        <button type="button" data-test="intent-cancel" :disabled="applying" @click="cancel">Zrušit</button>
      </div>
      <ul v-if="job?.notes.length" class="notes faint" data-test="intent-notes">
        <li v-for="(n, i) in job.notes" :key="i">Připomínka {{ i + 1 }}: {{ n }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.intent-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 1000px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h2 {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 18px;
}

h3 {
  margin: 0 0 4px;
  font-size: 14px;
  color: var(--dim);
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
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

.actions,
.task-actions {
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

.progress {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
}

.progress .state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.progress ol {
  margin: 8px 0 0;
  padding-left: 22px;
  color: var(--dim);
  font-size: 13px;
  max-height: 220px;
  overflow: auto;
}

.result {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary {
  margin: 0;
}

.step {
  display: flex;
  align-items: center;
  gap: 10px;
}

.level {
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--faint);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tasks {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0 0 0 18px;
  list-style: none;
  border-left: 1px solid var(--border);
}

.tasks > li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
}

.tasks > li > details {
  flex: 1;
  min-width: 0;
}

.tasks > li.removed {
  opacity: 0.5;
}

.tasks > li.removed .title {
  text-decoration: line-through;
}

summary {
  display: flex;
  gap: 10px;
  cursor: pointer;
}

.finding-count {
  margin-left: auto;
  color: var(--amber);
  font-size: 13px;
}

.meta {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 2px 12px;
  margin: 8px 0;
  font-size: 13px;
}

.meta dt {
  color: var(--faint);
}

.meta dd {
  margin: 0;
}

.findings {
  color: var(--amber);
}

.findings ul,
ul.findings {
  margin: 4px 0;
  padding-left: 20px;
}

.edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.applied p {
  margin: 0;
}

.warning {
  color: var(--amber);
}

.notes {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
}

.mono {
  font-family: var(--mono);
  font-size: 14px;
}
</style>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Ban, PauseCircle, Play, PlayCircle, X } from 'lucide-vue-next'
import {
  levelLabel,
  levelNoun,
  linkActionKey,
  splitIds,
  DEFERRABLE_STATES,
  type EditTaskInput,
  type RunInput,
  type LinkInput,
  type RunPanel,
  type TaskDetail,
  type WriteError,
} from '@/lib/backlog'
import { fmtTime } from '@/lib/format'
import { reviewHref, runHref, taskHref } from '@/lib/router'
import { prStateLabel, shownState } from '@/lib/runs'
import StatusChip from '@/components/runs/StatusChip.vue'
import IssueList from './IssueList.vue'
import RunDialog from './RunDialog.vue'
import StateChip from './StateChip.vue'
import TaskForm from './TaskForm.vue'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import CodeTip from '@/components/ui/CodeTip.vue'
import { useLevels } from '@/lib/names'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useConfirm } from '@/lib/confirm'
import Spinner from '@/components/ui/Spinner.vue'
import type { SelectOption } from '@/lib/select'

const props = defineProps<{
  detail: TaskDetail
  workflows: string[]
  busy: boolean
  error: WriteError | null
  run?: RunPanel
  /** Key of the running write (BacklogView `busyAction`): its button shows the spinner. */
  action?: string | null
  /** A kanban queue write (exclusion) is running. */
  queueBusy?: boolean
}>()

const emit = defineEmits<{
  edit: [input: EditTaskInput]
  /** Cancel the task (status `cancelled`), confirmed by the user. */
  'cancel-task': []
  link: [input: LinkInput]
  'assign-workflow': [workflow: string | null]
  'open-run': []
  'run-start': [input: RunInput & { force: boolean }]
  'run-cancel': []
  'run-commit': []
  /** Exclude the task from auto continue or return it to the queue. */
  exclude: [id: string, excluded: boolean]
}>()

const editing = ref(false)
const dependsInput = ref('')
const relatedInput = ref('')
const workflowChoice = ref(props.detail.task.own_workflow ?? '')
const workflowOptions = computed<SelectOption[]>(() => [
  { value: '', label: 'Zděděno' },
  ...props.workflows.map((w) => ({ value: w, label: w })),
])

const task = computed(() => props.detail.task)
const level = useLevels()
/** `Task nemá workflow – nastav ho na tasku, stepu nebo projektu.` with the configured levels. */
const NO_WORKFLOW_HINT = computed(() => {
  const where = [...level.levels.value].reverse().map((l) => levelNoun(l, 'gen'))
  const last = where.pop() ?? ''
  const list = where.length ? `${where.join(', ')} nebo ${last}` : last
  return `${levelLabel(level.task.value)} nemá workflow – nastav ho na ${list}.`
})
const linkPlaceholder = computed(
  () => `id ${levelNoun(level.task.value, 'gen')} nebo ${levelNoun(level.step.value, 'gen')}`,
)
const noWorkflow = computed(() => !task.value.workflow)
/** A done or cancelled task never runs again. */
const finished = computed(() => ['done', 'cancelled'].includes(task.value.board_state))
const runTooltip = computed(() => {
  if (finished.value) {
    const noun = levelLabel(level.task.value)
    return task.value.board_state === 'done' ? `${noun} je hotový, znovu se nespouští.` : `${noun} je zrušený, nespouští se.`
  }
  return noWorkflow.value ? NO_WORKFLOW_HINT.value : ''
})
const runBlocked = computed(() => noWorkflow.value || finished.value)
/** The task can wait in the auto-continue queue (it has not started). */
const queueable = computed(() => DEFERRABLE_STATES.includes(task.value.board_state))

const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()

/** Asks first, then sets status `cancelled` on a task that has not started (Zrušeno column). */
async function cancelTask() {
  const noun = levelNoun(level.task.value)
  const ok = await ask({
    title: `Zrušit ${noun} ${task.value.id}?`,
    message: `${levelLabel(level.task.value)} se přesune do sloupce Zrušeno a nespustí se. Vrátit ho jde úpravou statusu.`,
    confirmLabel: `Zrušit ${noun}`,
    cancelLabel: 'Ponechat',
    tone: 'danger',
  })
  if (ok) emit('cancel-task')
}

/** An edit was submitted: the next detail (after the write) closes the form. */
let saving = false

watch(
  () => props.detail,
  (next, previous) => {
    const sameTask = next.task.id === previous?.task.id
    // a live refresh of the same task must not close a form being edited
    if (!sameTask || saving || !editing.value) {
      editing.value = false
      saving = false
    }
    if (!sameTask || next.task.own_workflow !== previous?.task.own_workflow) {
      workflowChoice.value = next.task.own_workflow ?? ''
    }
  },
)

watch(
  () => props.error,
  (error) => {
    if (error) saving = false
  },
)

function addLink(key: 'depends_on' | 'related') {
  const source = key === 'depends_on' ? dependsInput : relatedInput
  const ids = splitIds(source.value)
  if (!ids.length) return
  emit('link', { [key]: ids })
  source.value = ''
}

function unlinkKey(key: 'depends_on' | 'related', id: string): string {
  return linkActionKey({ [key]: [id], remove: true })
}

function removeLink(key: 'depends_on' | 'related', id: string) {
  emit('link', { [key]: [id], remove: true })
}

function assign() {
  emit('assign-workflow', workflowChoice.value || null)
}

function onEdit(input: EditTaskInput) {
  saving = true
  emit('edit', input)
}
</script>

<template>
  <article class="task-detail" :data-task="task.id">
    <header class="head">
      <div class="title-row">
        <span class="id" data-test="task-id">{{ task.id }}</span>
        <h2 data-test="task-title">{{ task.title }}</h2>
        <StateChip :state="task.board_state" :blocked-by="task.blocked_by" />
        <div class="head-buttons">
          <Tooltip :text="runTooltip">
            <button
              type="button"
              class="run"
              :class="{ 'no-workflow': runBlocked }"
              data-test="run"
              :disabled="busy || run?.busy || run?.open || runBlocked"
              :aria-busy="run?.loading || undefined"
              @click="emit('open-run')"
            >
              <Spinner v-if="run?.loading" />
              <Play v-else :size="14" /> Spustit
            </button>
          </Tooltip>
          <button
            v-if="!editing"
            type="button"
            data-test="edit"
            :disabled="busy"
            @click="editing = true"
          >
            Upravit
          </button>
          <button
            v-if="queueable"
            type="button"
            class="cancel-task"
            data-test="cancel-task"
            :disabled="busy || run?.busy || run?.open"
            :aria-busy="action === 'cancel' || undefined"
            @click="cancelTask"
          >
            <Spinner v-if="action === 'cancel'" />
            <Ban v-else :size="14" /> Zrušit
          </button>
        </div>
      </div>
      <dl class="meta">
        <dt>Soubor</dt>
        <dd class="mono" data-test="path">{{ task.path }}</dd>
        <dt>Workflow</dt>
        <dd data-test="workflow">
          {{ task.workflow ?? 'bez workflow' }}
          <span v-if="task.workflow && !task.own_workflow" class="faint">(zděděno)</span>
        </dd>
        <dt>Writes</dt>
        <dd class="mono" data-test="writes">{{ task.writes.join(', ') || '—' }}</dd>
        <dt>Auto-merge</dt>
        <dd data-test="auto-merge">
          {{ task.effective_auto_merge ? 'zapnuto' : 'vypnuto' }}
          <span class="faint">{{ task.own_auto_merge == null ? '(zděděno)' : '(vlastní)' }}</span>
        </dd>
        <template v-if="queueable">
          <dt>Auto continue</dt>
          <dd data-test="auto-queue">
            <span data-test="auto-queue-state">{{ task.auto_excluded ? 'odloženo' : 've frontě' }}</span>
            <button
              type="button"
              class="queue-toggle"
              data-test="auto-queue-toggle"
              :disabled="queueBusy"
              @click="emit('exclude', task.id, !task.auto_excluded)"
            >
              <PlayCircle v-if="task.auto_excluded" :size="14" />
              <PauseCircle v-else :size="14" />
              {{ task.auto_excluded ? 'Vrátit do auto continue' : 'Vyloučit z auto continue' }}
            </button>
          </dd>
        </template>
      </dl>
      <ul v-if="detail.issues.length" class="task-issues" data-test="task-issues">
        <li v-for="(issue, n) in detail.issues" :key="n">{{ issue.code }}: {{ issue.message }}</li>
      </ul>
    </header>

    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />

    <RunDialog
      v-if="run?.open"
      :check="run.check"
      :task="task"
      :body="detail.body"
      :loading="run.loading"
      :busy="run.busy"
      :error="run.error"
      :result="run.result"
      :action="run.action"
      :waiting="run.waiting"
      @start="emit('run-start', $event)"
      @cancel="emit('run-cancel')"
      @commit="emit('run-commit')"
    />

    <TaskForm
      v-if="editing"
      :key="`${task.path}:${task.title}`"
      mode="edit"
      :steps="[]"
      :workflows="workflows"
      :task="task"
      :task-body="detail.body"
      :busy="busy"
      :pending="action === 'edit'"
      :error="error"
      @submit="onEdit($event as EditTaskInput)"
      @cancel="editing = false"
    />
    <IssueList v-else-if="error" :message="error.message" :issues="error.issues" />

    <section class="section">
      <h3>Zadání</h3>
      <MarkdownView :source="detail.body" data-test="body" />
    </section>

    <section class="section links">
      <h3>Vazby</h3>
      <div class="link-group" data-test="depends">
        <h4>Závisí na</h4>
        <ul v-if="detail.depends.length">
          <li v-for="dep in detail.depends" :key="dep.id" :data-dep="dep.id">
            <a v-if="dep.kind === 'task'" :href="taskHref(dep.id)" class="mono">{{ dep.id }}</a>
            <span v-else class="mono">{{ dep.id }}</span>
            <span v-if="dep.title">{{ dep.title }}</span>
            <span class="faint" data-test="dep-state">{{ dep.state }}</span>
            <Tooltip text="Odebrat vazbu">
              <button
                type="button"
                class="icon"
                :data-test="`unlink-${dep.id}`"
                :disabled="busy"
                aria-label="Odebrat vazbu"
                :aria-busy="action === unlinkKey('depends_on', dep.id) || undefined"
                @click="removeLink('depends_on', dep.id)"
              >
                <Spinner v-if="action === unlinkKey('depends_on', dep.id)" />
                <X v-else :size="14" />
              </button>
            </Tooltip>
          </li>
        </ul>
        <p v-else class="faint">Žádné závislosti</p>
        <div class="add">
          <input v-model="dependsInput" data-test="link-input" type="text" :placeholder="linkPlaceholder" />
          <button
            type="button"
            data-test="link-add"
            :disabled="busy"
            :aria-busy="action === 'link:depends_on' || undefined"
            @click="addLink('depends_on')"
          >
            <Spinner v-if="action === 'link:depends_on'" />
            Přidat
          </button>
        </div>
      </div>

      <div class="link-group" data-test="blocks">
        <h4>Blokuje</h4>
        <ul v-if="detail.blocks.length">
          <li v-for="b in detail.blocks" :key="b.id" :data-block="b.id">
            <a :href="taskHref(b.id)" class="mono">{{ b.id }}</a>
            <span>{{ b.title }}</span>
            <StateChip :state="b.board_state" />
          </li>
        </ul>
        <p v-else class="faint">Nic</p>
      </div>

      <div class="link-group" data-test="related">
        <h4>Související</h4>
        <ul v-if="task.related.length">
          <li v-for="r in task.related" :key="r" :data-related="r">
            <a :href="taskHref(r)" class="mono">{{ r }}</a>
            <Tooltip text="Odebrat vazbu">
              <button
                type="button"
                class="icon"
                :data-test="`unrelate-${r}`"
                :disabled="busy"
                aria-label="Odebrat vazbu"
                :aria-busy="action === unlinkKey('related', r) || undefined"
                @click="removeLink('related', r)"
              >
                <Spinner v-if="action === unlinkKey('related', r)" />
                <X v-else :size="14" />
              </button>
            </Tooltip>
          </li>
        </ul>
        <p v-else class="faint">Nic</p>
        <div class="add">
          <input v-model="relatedInput" data-test="related-input" type="text" placeholder="id" />
          <button
            type="button"
            data-test="related-add"
            :disabled="busy"
            :aria-busy="action === 'link:related' || undefined"
            @click="addLink('related')"
          >
            <Spinner v-if="action === 'link:related'" />
            Přidat
          </button>
        </div>
      </div>
    </section>

    <section class="section">
      <h3>Workflow</h3>
      <div class="add">
        <button type="button" :disabled="busy || ['done', 'cancelled', 'running', 'in review'].includes(task.board_state)" @click="editing = true">Upravit a navrhnout workflow</button>
        <SelectMenu
          v-model="workflowChoice"
          data-test="workflow-select"
          label="Workflow"
          :options="workflowOptions"
        />
        <button
          type="button"
          data-test="assign"
          :disabled="busy"
          :aria-busy="action === 'assign' || undefined"
          @click="assign"
        >
          <Spinner v-if="action === 'assign'" />
          Přiřadit
        </button>
      </div>
    </section>

    <section class="section">
      <h3>Běhy</h3>
      <table v-if="detail.runs.length" class="table" data-test="runs">
        <thead>
          <tr>
            <th>Běh</th>
            <th>Stav</th>
            <th>Větev</th>
            <th>Začátek</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in detail.runs" :key="run.run_id" :data-run="run.run_id">
            <td><a :href="runHref(run.run_id)" class="mono">{{ run.run_id }}</a></td>
            <td><StatusChip :status="shownState(run)" /></td>
            <td class="mono">{{ run.branch }}</td>
            <td>{{ fmtTime(run.started_at) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="faint" data-test="no-runs">Žádné běhy</p>
    </section>

    <section class="section">
      <h3>PR</h3>
      <ul v-if="detail.prs.length" data-test="prs">
        <li v-for="pr in detail.prs" :key="pr.branch" :data-pr="pr.pr_id">
          <span class="pr-state" data-test="pr-state">{{ prStateLabel(pr.state) }}</span>
          <CodeTip :code="pr.task_id">
            <a :href="pr.url" target="_blank" rel="noopener" data-test="pr-link">#{{ pr.pr_id }} {{ pr.title }}</a>
          </CodeTip>
          <a :href="reviewHref(pr.task_id)" data-test="pr-review">Review</a>
          <span class="mono faint">{{ pr.branch }}</span>
        </li>
      </ul>
      <p v-else class="faint" data-test="no-prs">Žádné PR</p>
    </section>
  </article>
</template>

<style scoped>
.task-detail {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

h2 {
  margin: 0;
  font-size: 22px;
}

h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--dim);
}

h4 {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--faint);
}

.id,
.mono {
  font-family: var(--mono);
  font-size: 14px;
}

.id {
  color: var(--dim);
}

.meta {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 16px;
  margin: 12px 0 0;
}

dt {
  color: var(--faint);
}

dd {
  margin: 0;
}

.task-issues {
  color: var(--amber);
}

.section {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.links {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.links h3 {
  grid-column: 1 / -1;
  margin-bottom: 0;
}

ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}

.add {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

input {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
}

button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

button.queue-toggle {
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 13px;
}

button.icon {
  display: inline-flex;
  padding: 2px 4px;
}

.head-buttons {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

button.cancel-task {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

button.run {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-color: rgba(108, 182, 255, 0.6);
  color: var(--blue);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}

/* A disabled button gets no mouse events; let the tooltip anchor get the hover. */
button.run.no-workflow {
  pointer-events: none;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-soft);
  text-align: left;
}

th {
  color: var(--faint);
  font-weight: 600;
  font-size: 14px;
}

.pr-state {
  text-transform: uppercase;
  font-size: 12px;
  color: var(--purple);
}
</style>

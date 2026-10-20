<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CornerDownRight,
  GitBranchPlus,
  GitPullRequest,
  History,
  Info,
  Link2,
  PauseCircle,
  Pencil,
  Play,
  PlayCircle,
  Settings2,
  Wand2,
  X,
} from 'lucide-vue-next'
import {
  canStackDependencies,
  fetchBacklog,
  type DependsRef,
  taskInProgress,
  isDoneState,
  blockedTooltip,
  levelLabel,
  levelNoun,
  linkActionKey,
  unmetLine,
  DEFERRABLE_STATES,
  STATE_LABELS,
  type EditTaskInput,
  type FollowUpResult,
  type RunInput,
  type LinkInput,
  type RunPanel,
  type TaskDetail,
  type WriteError,
} from '@/lib/backlog'
import { fmtTime } from '@/lib/format'
import { reviewHref, runHref, taskHref } from '@/lib/router'
import { canRetry, prStateLabel, shownState } from '@/lib/runs'
import RetryRunButton from '@/components/runs/RetryRunButton.vue'
import StatusChip from '@/components/runs/StatusChip.vue'
import FollowUpDialog from './FollowUpDialog.vue'
import IssueList from './IssueList.vue'
import RunDialog from './RunDialog.vue'
import StateChip from './StateChip.vue'
import TaskDocuments from './TaskDocuments.vue'
import TaskForm from './TaskForm.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import CodeTip from '@/components/ui/CodeTip.vue'
import { useLevels, useNames } from '@/lib/names'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useConfirm } from '@/lib/confirm'
import Spinner from '@/components/ui/Spinner.vue'

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
  'open-run': []
  'run-start': [input: RunInput & { force: boolean }]
  'run-cancel': []
  'run-commit': []
  /** Exclude the task from auto continue or return it to the queue. */
  exclude: [id: string, excluded: boolean]
  /** A failed or stopped run was continued (`factory task retry`). */
  retried: []
  /** A task that follows this done task was created (and maybe started). */
  'follow-up': [result: FollowUpResult]
}>()

const editing = ref(false)
/** The form was opened by "Vylepšit agentem": it starts the agent at once. */
const autoImprove = ref(false)

const task = computed(() => props.detail.task)
const level = useLevels()
/** `Task nemá workflow – nastav ho na tasku, stepu nebo projektu.` with the configured levels. */
const NO_WORKFLOW_HINT = computed(() => {
  const where = [...level.levels.value].reverse().map((l) => levelNoun(l, 'gen'))
  const last = where.pop() ?? ''
  const list = where.length ? `${where.join(', ')} nebo ${last}` : last
  return `${levelLabel(level.task.value)} nemá workflow – nastav ho na ${list}.`
})
const noWorkflow = computed(() => !task.value.workflow)
/** A person's task (`assignee: human`): no run starts it, the person marks it done. */
const forHuman = computed(() => task.value.assignee === 'human')
const HUMAN_HINT = 'Task udělá člověk, factory ho nespustí. Až bude hotový, označ ho jako hotový.'
/** A done or cancelled task never runs again. */
const finished = computed(() => isDoneState(task.value.board_state))
/** A done task is not run, edited or improved again: a follow-up task continues it. */
const done = computed(() => task.value.board_state === 'done')
const followUpOpen = ref(false)
const followers = computed(() => props.detail.followed_by ?? [])

function onFollowUpCreated(result: FollowUpResult) {
  followUpOpen.value = false
  emit('follow-up', result)
}
const inProgress = computed(() => taskInProgress(task.value.board_state))
// Container dependencies list unfinished task IDs but no states in the detail.
// Resolve those states from the board; until it loads, keep the start disabled.
const containerDependencies = ref<DependsRef[]>([])
watch(
  () => props.detail,
  async (detail, _previous, onCleanup) => {
    containerDependencies.value = []
    if (!detail.task.blocked_by.some((u) => u.reason === 'incomplete')) return
    let current = true
    onCleanup(() => { current = false })
    try {
      const backlog = await fetchBacklog()
      if (current) containerDependencies.value = backlog.tasks.map((t) => ({
        id: t.id, kind: 'task', title: t.title, state: t.board_state,
      }))
    } catch {
      // An unavailable board cannot establish that every blocker has an open PR.
    }
  },
  { immediate: true },
)
const dependenciesBlocked = computed(() =>
  (task.value.board_state === 'blocked' || task.value.blocked_by.length > 0) &&
  !canStackDependencies(task.value.blocked_by, [...props.detail.depends, ...containerDependencies.value]),
)
const runTooltip = computed(() => {
  if (inProgress.value) return task.value.board_state === 'running' ? 'Task právě běží.' : 'Task čeká na review/merge PR.'
  if (dependenciesBlocked.value) return blockedTooltip(task.value.blocked_by, names.value) || 'Task je blokovaný.'

  if (finished.value) {
    const noun = levelLabel(level.task.value)
    return task.value.board_state === 'done' ? `${noun} je hotový, znovu se nespouští.` : `${noun} je zrušený, nespouští se.`
  }
  if (forHuman.value) return HUMAN_HINT
  return noWorkflow.value ? NO_WORKFLOW_HINT.value : ''
})
const runBlocked = computed(() => noWorkflow.value || finished.value || forHuman.value || inProgress.value || dependenciesBlocked.value)
/** The task can wait in the auto-continue queue (it has not started). */
const queueable = computed(() => DEFERRABLE_STATES.includes(task.value.board_state))
/** Advice is offered only for a task that has not started. */
const adviceBlocked = computed(() => finished.value || inProgress.value)
const improveTooltip = computed(() => (adviceBlocked.value ? `${levelLabel(level.task.value)} už nejde měnit.` : ''))

function openEdit(improve: boolean) {
  if (inProgress.value || (improve && adviceBlocked.value)) return
  autoImprove.value = improve
  editing.value = true
}

function closeEdit() {
  editing.value = false
  autoImprove.value = false
}

const { names } = useNames()

type Readiness = { tone: 'ok' | 'warn' | 'muted'; title: string; reasons: string[]; runId: string | null }

/** Informational banner: can the task run, and what stops it. Does not change `runBlocked`. */
const readiness = computed<Readiness>(() => {
  const state = task.value.board_state
  if (finished.value) return { tone: 'muted', title: runTooltip.value, reasons: [], runId: null }
  if (inProgress.value) {
    return {
      tone: 'muted',
      title: `${levelLabel(level.task.value)} je ve stavu ${STATE_LABELS[state]}.`,
      reasons: [],
      runId: props.detail.runs[0]?.run_id ?? null,
    }
  }
  if (state === 'human') return { tone: 'muted', title: HUMAN_HINT, reasons: [], runId: null }
  const reasons: string[] = []
  if (forHuman.value) reasons.push(HUMAN_HINT)
  else if (noWorkflow.value) reasons.push(NO_WORKFLOW_HINT.value)
  for (const u of task.value.blocked_by) reasons.push(unmetLine(u, names.value))
  if (task.value.invalid || props.detail.issues.length) reasons.push('Soubor má chyby – oprav je před spuštěním.')
  if (!reasons.length) return { tone: 'ok', title: 'Připraveno ke spuštění', reasons, runId: null }
  return { tone: 'warn', title: 'Před spuštěním je potřeba:', reasons, runId: null }
})

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
    // Preserve a draft across live refreshes while the task remains editable.
    if (!sameTask || saving || !editing.value || inProgress.value || finished.value) {
      closeEdit()
      saving = false
    }
    if (!sameTask) followUpOpen.value = false
  },
)

watch(
  () => props.error,
  (error) => {
    if (error) saving = false
  },
)

function unlinkKey(key: 'depends_on' | 'related', id: string): string {
  return linkActionKey({ [key]: [id], remove: true })
}

function removeLink(key: 'depends_on' | 'related', id: string) {
  if (inProgress.value) return
  emit('link', { [key]: [id], remove: true })
}

function onEdit(input: EditTaskInput) {
  if (inProgress.value) return
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
        <StateChip :state="task.board_state" :blocked-by="task.blocked_by" :waits-for-human="task.waits_for_human" />
        <div class="head-buttons">
          <button
            v-if="done"
            type="button"
            class="run"
            data-test="follow-up"
            :disabled="busy || followUpOpen"
            @click="followUpOpen = true"
          >
            <GitBranchPlus :size="14" /> Navázat follow-upem
          </button>
          <Tooltip v-if="!done" :text="runTooltip">
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
          <Tooltip v-if="!editing && !done" :text="inProgress ? improveTooltip : ''">
            <button
              type="button"
              data-test="edit"
              :disabled="busy || inProgress"
              @click="openEdit(false)"
            >
              <Pencil :size="14" /> Upravit
            </button>
          </Tooltip>
          <Tooltip v-if="forHuman && !finished" :text="inProgress ? improveTooltip : ''">
            <button
              type="button"
              data-test="mark-done"
              :disabled="busy || inProgress"
              @click="onEdit({ status: 'done' })"
            >
              <CheckCircle2 :size="14" /> Hotovo
            </button>
          </Tooltip>
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
          <Tooltip v-if="!editing && !done" :text="improveTooltip">
            <button
              type="button"
              class="btn-improve"
              data-test="improve"
              :disabled="busy || adviceBlocked"
              @click="openEdit(true)"
            >
              <Wand2 :size="18" /> Vylepšit agentem
            </button>
          </Tooltip>
        </div>
      </div>
      <div class="path mono" data-test="path">{{ task.path }}</div>
      <div v-if="detail.follows" class="follows" data-test="follows">
        <CornerDownRight :size="14" aria-hidden="true" />
        Navazuje na
        <a v-if="detail.follows.kind === 'task'" :href="taskHref(detail.follows.id)" class="mono">{{ detail.follows.id }}</a>
        <span v-else class="mono">{{ detail.follows.id }}</span>
        <span v-if="detail.follows.title" class="ellipsis">{{ detail.follows.title }}</span>
      </div>
      <div v-if="detail.issues.length" class="task-issues" data-test="task-issues">
        <AlertTriangle :size="16" class="issues-icon" />
        <ul>
          <li v-for="(issue, n) in detail.issues" :key="n">{{ issue.code }}: {{ issue.message }}</li>
        </ul>
      </div>
    </header>

    <div class="readiness" :class="`tone-${readiness.tone}`" data-test="run-readiness" :data-tone="readiness.tone">
      <CheckCircle2 v-if="readiness.tone === 'ok'" :size="18" class="readiness-icon" />
      <AlertTriangle v-else-if="readiness.tone === 'warn'" :size="18" class="readiness-icon" />
      <Info v-else :size="18" class="readiness-icon" />
      <div class="readiness-text">
        <strong>{{ readiness.title }}</strong>
        <span v-if="readiness.tone === 'ok'">
          · workflow <b class="mono">{{ task.workflow }}</b>
        </span>
        <a v-if="readiness.runId" :href="runHref(readiness.runId)" class="mono">· běh {{ readiness.runId }}</a>
        <ul v-if="readiness.reasons.length" class="reasons">
          <li v-for="(reason, n) in readiness.reasons" :key="n" data-test="readiness-reason">{{ reason }}</li>
        </ul>
      </div>
    </div>

    <ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />

    <FollowUpDialog
      v-if="followUpOpen && done"
      :task-id="task.id"
      :task-title="task.title"
      @created="onFollowUpCreated"
      @cancel="followUpOpen = false"
    />

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
      :start-disabled="runBlocked"
      @start="emit('run-start', $event)"
      @cancel="emit('run-cancel')"
      @commit="emit('run-commit')"
    />

    <div class="body-grid">
      <div class="main">
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
          :auto-improve="autoImprove"
          @submit="onEdit($event as EditTaskInput)"
          @cancel="closeEdit"
        />
        <template v-else>
          <IssueList v-if="error" :message="error.message" :issues="error.issues" />
          <TaskDocuments :task-id="task.id" :body="detail.body" />
        </template>

        <section class="card">
          <h3><History :size="16" /> Běhy <span class="count">{{ detail.runs.length }}</span></h3>
          <table v-if="detail.runs.length" class="table" data-test="runs">
            <thead>
              <tr>
                <th>Běh</th>
                <th>Stav</th>
                <th>Větev</th>
                <th class="right">Začátek</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(run, index) in detail.runs" :key="run.run_id" :data-run="run.run_id">
                <td><a :href="runHref(run.run_id)" class="mono">{{ run.run_id }}</a></td>
                <td><StatusChip :status="shownState(run)" /></td>
                <td class="mono branch">{{ run.branch }}</td>
                <td class="right nowrap">{{ fmtTime(run.started_at) }}</td>
                <td class="right">
                  <RetryRunButton
                    v-if="index === 0 && canRetry(run) && !finished && !inProgress"
                    :run-id="run.run_id"
                    @started="emit('retried')"
                  />
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="faint" data-test="no-runs">Žádné běhy</p>
        </section>

        <section class="card">
          <h3><GitPullRequest :size="16" /> PR <span class="count">{{ detail.prs.length }}</span></h3>
          <ul v-if="detail.prs.length" class="pr-list" data-test="prs">
            <li v-for="pr in detail.prs" :key="pr.branch" :data-pr="pr.pr_id">
              <span class="pr-state" data-test="pr-state">{{ prStateLabel(pr.state) }}</span>
              <CodeTip :code="pr.task_id">
                <a :href="pr.url" target="_blank" rel="noopener" data-test="pr-link">#{{ pr.pr_id }} {{ pr.title }}</a>
              </CodeTip>
              <a :href="reviewHref(pr.task_id)" class="pill-link" data-test="pr-review">Review</a>
              <span class="mono faint pr-branch">{{ pr.branch }}</span>
            </li>
          </ul>
          <p v-else class="faint" data-test="no-prs">Žádné PR</p>
        </section>
      </div>

      <aside class="side">
        <section class="card">
          <h3><Settings2 :size="16" /> Nastavení</h3>
          <dl class="props">
            <dt>Workflow</dt>
            <dd data-test="workflow">
              <span v-if="task.workflow" class="mono">{{ task.workflow }}</span>
              <span v-else class="amber">bez workflow</span>
              <span v-if="task.workflow && !task.own_workflow" class="faint"> (zděděno)</span>
            </dd>
            <dt>Auto-merge</dt>
            <dd data-test="auto-merge">
              {{ task.effective_auto_merge ? 'zapnuto' : 'vypnuto' }}
              <span class="faint">{{ task.own_auto_merge == null ? '(zděděno)' : '(vlastní)' }}</span>
            </dd>
            <dt>Writes</dt>
            <dd data-test="writes">
              <span v-if="task.writes.length" class="chips">
                <span v-for="w in task.writes" :key="w" class="chip mono">{{ w }}</span>
              </span>
              <span v-else>—</span>
            </dd>
            <template v-if="queueable">
              <dt>Auto continue</dt>
              <dd data-test="auto-queue">
                <span data-test="auto-queue-state">{{ task.auto_excluded ? 'odloženo' : 've frontě' }}</span>
                <button
                  type="button"
                  class="queue-toggle wide"
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
        </section>

        <section class="card">
          <h3><Link2 :size="16" /> Vazby</h3>
          <div class="link-group" data-test="depends">
            <h4>Závisí na <span class="count">{{ detail.depends.length }}</span></h4>
            <ul v-if="detail.depends.length">
              <li v-for="dep in detail.depends" :key="dep.id" :data-dep="dep.id">
                <a v-if="dep.kind === 'task'" :href="taskHref(dep.id)" class="mono">{{ dep.id }}</a>
                <span v-else class="mono">{{ dep.id }}</span>
                <span v-if="dep.title" class="ellipsis">{{ dep.title }}</span>
                <span class="faint small" data-test="dep-state">{{ dep.state }}</span>
                <span class="push"><Tooltip :text="inProgress ? improveTooltip : 'Odebrat vazbu'">
                  <button
                    type="button"
                    class="icon"
                    :data-test="`unlink-${dep.id}`"
                    :disabled="busy || inProgress"
                    aria-label="Odebrat vazbu"
                    :aria-busy="action === unlinkKey('depends_on', dep.id) || undefined"
                    @click="removeLink('depends_on', dep.id)"
                  >
                    <Spinner v-if="action === unlinkKey('depends_on', dep.id)" />
                    <X v-else :size="14" />
                  </button>
                </Tooltip></span>
              </li>
            </ul>
            <p v-else class="faint">Žádné závislosti</p>
          </div>

          <div class="link-group" data-test="blocks">
            <h4>Blokuje <span class="count">{{ detail.blocks.length }}</span></h4>
            <ul v-if="detail.blocks.length">
              <li v-for="b in detail.blocks" :key="b.id" :data-block="b.id">
                <a :href="taskHref(b.id)" class="mono">{{ b.id }}</a>
                <span class="ellipsis">{{ b.title }}</span>
                <span class="push"><StateChip :state="b.board_state" /></span>
              </li>
            </ul>
            <p v-else class="faint">Nic</p>
          </div>

          <div v-if="followers.length" class="link-group" data-test="followed-by">
            <h4>Navazují na něj <span class="count">{{ followers.length }}</span></h4>
            <ul>
              <li v-for="f in followers" :key="f.id" :data-follower="f.id">
                <a :href="taskHref(f.id)" class="mono">{{ f.id }}</a>
                <span class="ellipsis">{{ f.title }}</span>
                <span class="push"><StateChip :state="f.board_state" /></span>
              </li>
            </ul>
          </div>

          <div class="link-group" data-test="related">
            <h4>Související <span class="count">{{ task.related.length }}</span></h4>
            <ul v-if="task.related.length">
              <li v-for="r in task.related" :key="r" :data-related="r">
                <a :href="taskHref(r)" class="mono">{{ r }}</a>
                <span class="push"><Tooltip :text="inProgress ? improveTooltip : 'Odebrat vazbu'">
                  <button
                    type="button"
                    class="icon"
                    :data-test="`unrelate-${r}`"
                    :disabled="busy || inProgress"
                    aria-label="Odebrat vazbu"
                    :aria-busy="action === unlinkKey('related', r) || undefined"
                    @click="removeLink('related', r)"
                  >
                    <Spinner v-if="action === unlinkKey('related', r)" />
                    <X v-else :size="14" />
                  </button>
                </Tooltip></span>
              </li>
            </ul>
            <p v-else class="faint">Nic</p>
          </div>
        </section>
      </aside>
    </div>
  </article>
</template>

<style scoped>
.task-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* header */
.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
}

h2 {
  margin: 0;
  font-size: 22px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.id,
.mono {
  font-family: var(--mono);
  font-size: 14px;
}

.id {
  color: var(--dim);
}

.path {
  margin-top: 6px;
  font-size: 13px;
  color: var(--faint);
  overflow-wrap: anywhere;
}

.head-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.follows {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  min-width: 0;
  color: var(--dim);
}

.task-issues {
  display: flex;
  gap: 10px;
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--amber) 55%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--amber) 8%, var(--panel));
  color: var(--amber);
}

.issues-icon {
  flex: none;
  margin-top: 2px;
}

/* readiness banner */
.readiness {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: 10px;
  background: var(--panel);
}

.readiness-icon {
  flex: none;
  margin-top: 1px;
}

.readiness-text {
  min-width: 0;
}

.readiness-text a {
  margin-left: 6px;
}

.readiness .reasons {
  margin-top: 4px;
  list-style: disc;
  padding-left: 18px;
}

.readiness .reasons li {
  display: list-item;
  padding: 1px 0;
}

.tone-ok {
  border-left-color: var(--green);
  background: color-mix(in srgb, var(--green) 8%, var(--panel));
}

.tone-ok .readiness-icon {
  color: var(--green);
}

.tone-warn {
  border-left-color: var(--amber);
  background: color-mix(in srgb, var(--amber) 8%, var(--panel));
}

.tone-warn .readiness-icon {
  color: var(--amber);
}

.tone-muted {
  border-left-color: var(--faint);
  color: var(--dim);
}

.tone-muted .readiness-icon {
  color: var(--faint);
}

/* two-column body */
.body-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
  align-items: start;
}

.main,
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

@media (max-width: 1100px) {
  .body-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.card {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
}

.card > h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 15px;
  letter-spacing: 0.04em;
  color: var(--dim);
}

.card > h3 svg {
  color: var(--faint);
}

.count {
  color: var(--faint);
  font-weight: 400;
}

h4 {
  display: flex;
  gap: 6px;
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--faint);
}

/* properties of the run */
.props {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
}

dt {
  color: var(--faint);
}

dd {
  margin: 0;
  min-width: 0;
}

.amber {
  color: var(--amber);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

/* a long path without spaces wraps instead of growing past the card */
.chip {
  max-width: 100%;
  min-width: 0;
  overflow-wrap: anywhere;
  padding: 1px 6px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--panel-2);
  font-size: 12px;
}

/* links */
.link-group + .link-group {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border-soft);
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
  min-width: 0;
}

.ellipsis {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.small {
  font-size: 12px;
  white-space: nowrap;
}

.push {
  margin-left: auto;
}

/* buttons */
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

button.wide {
  justify-content: center;
  width: 100%;
}

button.queue-toggle {
  margin-top: 6px;
  padding: 2px 8px;
  font-size: 13px;
}

button.icon {
  display: inline-flex;
  padding: 2px 4px;
}

button.run {
  padding: 5px 16px;
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 18%, var(--panel));
  color: var(--blue);
  font-weight: 600;
}

button.cancel-task {
  border-color: transparent;
  background: transparent;
  color: var(--red);
}

button.cancel-task:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--red) 55%, transparent);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}

/* A disabled button gets no mouse events; let the tooltip anchor get the hover. */
button.run.no-workflow {
  pointer-events: none;
}

/* runs */
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

.right {
  text-align: right;
}

.nowrap {
  white-space: nowrap;
}

.branch {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* PRs */
.pr-list li {
  flex-wrap: wrap;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-soft);
}

.pr-list li:last-child {
  border-bottom: none;
}

.pr-state {
  text-transform: uppercase;
  font-size: 12px;
  color: var(--purple);
}

.pill-link {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}

.pr-branch {
  margin-left: auto;
  font-size: 12px;
}
</style>

<script setup lang="ts">
// The Backlog screen of repo <id> (#/r/<id>/backlog…): …/backlog (tree or kanban), …/backlog/new[/<step id>]
// (form, the step preselected), …/backlog/<task id>, …/backlog/graph/<project or step id> (dependency graph and
// the Nastavení panel), …/backlog/new-container[/<project id>] (form for a new project or step).
// …/backlog/new-step selects the parent project before creating a step.
import { computed, ref, watch } from 'vue'
import { Plus, RefreshCw } from 'lucide-vue-next'
import BackLink from '@/components/ui/BackLink.vue'
import BacklogFilters from '@/components/backlog/BacklogFilters.vue'
import BacklogTree from '@/components/backlog/BacklogTree.vue'
import DependencyGraph from '@/components/backlog/DependencyGraph.vue'
import IssueList from '@/components/backlog/IssueList.vue'
import KanbanBoard from '@/components/backlog/KanbanBoard.vue'
import TaskDetail from '@/components/backlog/TaskDetail.vue'
import TaskForm from '@/components/backlog/TaskForm.vue'
import ContainerForm from '@/components/backlog/ContainerForm.vue'
import ContainerSettings from '@/components/backlog/ContainerSettings.vue'
import {
  BOARD_STATES,
  addContainer,
  addTask,
  childLevel,
  editContainer,
  fetchContainer,
  isContainerDetail,
  childContainerIds,
  commitBacklog,
  editTask,
  fetchBacklog,
  fetchGraph,
  fetchRunCheck,
  fetchTask,
  filterKanban,
  flattenIssues,
  graphWithoutDone,
  hideDone as hideDoneSaved,
  isDoneState,
  levelLabel,
  levelNoun,
  levelsText,
  linkActionKey,
  linkTask,
  namesFromBacklog,
  newRun,
  presentStates,
  projectOptions,
  pruneDone,
  setHideDone,
  stateCounts,
  kanbanColumn,
  mergeQueueOrder,
  setAutoExcluded,
  setQueueOrder,
  startRun,
  type AddContainerInput,
  type AddTaskInput,
  type ContainerDetailData,
  type EditContainerInput,
  type BacklogData,
  type BacklogFilters as Filters,
  type BacklogMode,
  type ContainerGraph,
  type EditTaskInput,
  type LinkInput,
  type RunInput,
  type RunPanel,
  type TaskDetail as TaskDetailData,
  type WriteError,
  type WriteResult,
} from '@/lib/backlog'
import {
  touchesContainer,
  touchesTask,
  touchesWorkflows,
  useLive,
  type LiveFilesEvent,
  type LiveTraceEvent,
} from '@/lib/live'
import { isDbBusyText } from '@/lib/api'
import {
  GRAPH,
  NEW_CONTAINER,
  NEW_STEP,
  NEW_TASK,
  graphHref,
  here,
  newContainerHref,
  newStepHref,
  newTaskHref,
  runHref,
  taskHref,
  useRouteParams,
} from '@/lib/router'
import { mergeNames, setLevels, useLevels, useNames } from '@/lib/names'
import { useBacklogStatus } from '@/lib/backlogStatus'
import { useConfigStatus } from '@/lib/configStatus'
import { plural } from '@/lib/format'
import CodeTip from '@/components/ui/CodeTip.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const params = useRouteParams()
const backlogStatus = useBacklogStatus()
const configStatus = useConfigStatus()
const target = computed(() => params.value[0] ?? null)
const routeKey = computed(() => params.value.join('/'))
const isNew = computed(() => target.value === NEW_TASK)
const isGraph = computed(() => target.value === GRAPH)
const graphId = computed(() => (isGraph.value ? (params.value[1] ?? null) : null))
const isNewStep = computed(() => target.value === NEW_STEP)
const isNewContainer = computed(() => target.value === NEW_CONTAINER || isNewStep.value)
const selectedProject = ref('')
/** The project of a new step; null for a new project. */
const newParent = computed(() =>
  isNewStep.value
    ? (projects.value.find((p) => p.id === selectedProject.value)?.id ?? null)
    : isNewContainer.value ? (params.value[1] ?? null) : null,
)
/** `…/backlog/new/<step id>`: the step the new task form preselects. */
const newTaskStep = computed(() => (isNew.value ? (params.value[1] ?? null) : null))
const taskId = computed(() =>
  target.value && !isNew.value && !isGraph.value && !isNewContainer.value ? target.value : null,
)

const data = ref<BacklogData | null>(null)
const filters = ref<Filters>({})
const mode = ref<BacklogMode>('tree')
const detail = ref<TaskDetailData | null>(null)
/** The task id `detail` belongs to: a detail of another task is never shown. */
const detailFor = ref<string | null>(null)
/** The detail of the open task, or null while it loads after a switch. */
const shownDetail = computed(() =>
  detail.value && detailFor.value === taskId.value ? detail.value : null,
)
/** Number of the latest screen load: an answer of an older load is dropped. */
let loadSeq = 0
const loading = ref(false)
/** A new task waits for its own list load, even when a previous screen cached steps. */
const newTaskReady = ref(false)
const error = ref<string | null>(null)
const writeError = ref<WriteError | null>(null)
/** Key of the running write (`add`, `edit`, `assign`, `link:…`, `unlink:…`): its button spins. */
const busyAction = ref<string | null>(null)
const busy = computed(() => busyAction.value !== null)
const graph = ref<ContainerGraph | null>(null)
/** A kanban queue write (order, exclusion) is running. */
const queueBusy = ref(false)
/** The project or step of the graph page (Nastavení panel). */
const container = ref<ContainerDetailData | null>(null)
const containerError = ref<string | null>(null)
/** Key of the settings panel: a saved or reloaded change resets the form. */
const settingsKey = computed(() => {
  const c = container.value?.container
  return c ? JSON.stringify([c.id, c.title, c.own, c.effective]) : ''
})

function closedRun(): RunPanel {
  return {
    open: false,
    check: null,
    loading: false,
    busy: false,
    error: null,
    result: null,
    action: null,
    waiting: false,
  }
}

/** Runs of the task before the last start, to recognise the run a `pending` start launched. */
let knownRuns = new Set<string>()

/** A `pending` start waits for its run: once the task detail lists it, show the link. */
function claimPending(task: TaskDetailData) {
  const panel = run.value
  if (!panel.waiting || task.task.id !== taskId.value) return
  const found = newRun(task.runs, knownRuns)
  if (!found || !panel.result) return
  run.value = {
    ...panel,
    waiting: false,
    action: null,
    result: { ...panel.result, run: found, pending: false },
  }
}

function setDetail(id: string, task: TaskDetailData | null) {
  detail.value = task
  detailFor.value = task ? id : null
  if (task) claimPending(task)
}

const run = ref<RunPanel>(closedRun())

const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
const tasks = computed(() => (Array.isArray(data.value?.tasks) ? data.value.tasks : []))
const levels = computed(() => (Array.isArray(data.value?.levels) ? data.value.levels : []))
const level = useLevels()
// A loaded backlog refreshes the shared names (tooltips of codes) and levels at once.
watch(data, (next) => {
  if (!next) return
  setLevels(next.levels)
  mergeNames(namesFromBacklog(next.items, next.tasks))
})
const workflows = computed(() =>
  Array.isArray(data.value?.workflows) ? data.value.workflows : [],
)
const steps = computed(() => (Array.isArray(data.value?.steps) ? data.value.steps : []))
const states = computed(() =>
  Array.isArray(data.value?.states) && data.value.states.length ? data.value.states : BOARD_STATES,
)
const { names } = useNames()
/** The level of the container the form creates; null when the parent holds tasks only. */
const newLevel = computed(() =>
  childLevel(level.levels.value, newParent.value ? (names.value[newParent.value]?.level ?? null) : null),
)
/** The level of a step under the graph's container; null when it holds tasks only. */
const graphChildLevel = computed(() =>
  graph.value ? childLevel(level.levels.value, graph.value.container.level) : null,
)
const projects = computed(() => projectOptions(items.value, steps.value, names.value))
const listChildLevel = computed(() => childLevel(level.levels.value, level.top.value))
const projectChoices = computed(() => projects.value.map((p) => ({
  value: p.id,
  label: p.title ? `${p.id} – ${p.title}` : p.id,
})))
/** The „Skrýt hotové“ switch: Hotovo and Zrušeno tasks leave the tree, kanban and graph. */
const hideDone = ref(hideDoneSaved())
function onHideDone(on: boolean) {
  hideDone.value = on
  setHideDone(on)
}
const counts = computed(() => (data.value ? stateCounts(data.value) : null))
const treeItems = computed(() => (hideDone.value ? pruneDone(items.value) : items.value))
const kanbanTasks = computed(() => {
  const shown = filterKanban(tasks.value, items.value, filters.value)
  return hideDone.value ? shown.filter((t) => !isDoneState(t.board_state)) : shown
})
/** Kanban columns: Bez workflow only with a task in it, no Hotovo/Zrušeno when hidden. */
const kanbanStates = computed(() =>
  presentStates(states.value, counts.value ?? {}).filter((s) => !hideDone.value || !isDoneState(s)),
)
const shownGraph = computed(() =>
  graph.value && hideDone.value ? graphWithoutDone(graph.value) : graph.value,
)
const issues = computed(() => (Array.isArray(data.value?.issues) ? data.value.issues : []))
const problemsText = computed(() => {
  const n = issues.value.length
  return `Backlog má ${n} ${plural(n, 'problém', 'problémy', 'problémů')}.`
})
/** The „Skrýt hotové“ switch hides every task of a non-empty tree. */
const treeFiltered = computed(() => hideDone.value && items.value.length > 0 && treeItems.value.length === 0)
/** Codes of the containers beside the new project or step (the suggested code follows them). */
const newSiblings = computed(() => childContainerIds(items.value, newParent.value))
/** The graph's container holds tasks: its Nový task button preselects it. */
const graphStep = computed(() =>
  graph.value && graph.value.container.level === level.step.value ? graph.value.container.id : null,
)

function message(e: unknown): string {
  return flattenIssues(e).message
}

async function loadList() {
  const seq = ++loadSeq
  loading.value = true
  error.value = null
  try {
    const list = await fetchBacklog()
    if (seq === loadSeq) {
      data.value = list
      if (isNew.value) newTaskReady.value = true
    }
  } catch (e) {
    if (seq === loadSeq) error.value = `Backlog se nepodařilo načíst: ${message(e)}`
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function loadDetail(id: string) {
  const seq = ++loadSeq
  loading.value = true
  error.value = null
  // another task: drop the previous one at once, a reload of the same task keeps it shown
  if (detailFor.value !== id) setDetail(id, null)
  try {
    const [task, list] = await Promise.all([fetchTask(id), fetchBacklog()])
    if (seq !== loadSeq || taskId.value !== id) return
    data.value = list
    setDetail(id, task?.task ? task : null)
  } catch (e) {
    if (seq !== loadSeq || taskId.value !== id) return
    setDetail(id, null)
    error.value = `Task ${id} se nepodařilo načíst: ${message(e)}`
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function setContainer(next: unknown) {
  container.value = isContainerDetail(next) ? next : null
}

async function loadContainer(id: string, seq: number) {
  try {
    // the panel offers the workflows of the backlog list; load it when it is not loaded yet
    const [next, list] = await Promise.all([
      fetchContainer(id),
      data.value ? Promise.resolve(null) : fetchBacklog().catch(() => null),
    ])
    if (seq === loadSeq) {
      if (list) data.value = list
      setContainer(next)
      containerError.value = null
    }
  } catch (e) {
    if (seq !== loadSeq) return
    container.value = null
    containerError.value = `Nastavení ${id} se nepodařilo načíst: ${message(e)}`
  }
}

async function loadGraph(id: string) {
  const seq = ++loadSeq
  loading.value = true
  error.value = null
  const settings = loadContainer(id, seq)
  try {
    const next = await fetchGraph(id)
    await settings
    if (seq === loadSeq) graph.value = next
  } catch (e) {
    if (seq !== loadSeq) return
    graph.value = null
    error.value = `Graf ${id} se nepodařilo načíst: ${message(e)}`
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function reload() {
  writeError.value = null
  if (isGraph.value) {
    if (graphId.value) void loadGraph(graphId.value)
    else error.value = `Chybí id ${levelsText(level.containers.value, 'gen')}.`
  } else if (taskId.value) void loadDetail(taskId.value)
  else void loadList()
}

async function onSaveSettings(input: EditContainerInput) {
  const id = graphId.value
  if (!id) return
  const result = await write('settings', () => editContainer(id, input))
  if (!result) return
  setContainer({ ...(container.value ?? {}), container: result.container })
  try {
    graph.value = await fetchGraph(id)
  } catch (e) {
    error.value = `Graf ${id} se nepodařilo načíst: ${message(e)}`
  }
}

async function onAddContainer(input: AddContainerInput) {
  const result = await write('add-container', () => addContainer(input))
  if (result) window.location.hash = graphHref(result.container.id)
}

function cancelNewContainer() {
  window.location.hash = !isNewStep.value && newParent.value
    ? graphHref(newParent.value) : here('backlog')
}

/** Apply a queue change to the loaded tasks at once; give back a function that undoes it. */
function optimistic(change: (tasks: BacklogData['tasks']) => BacklogData['tasks']): () => void {
  const before = data.value
  if (before && Array.isArray(before.tasks)) data.value = { ...before, tasks: change(before.tasks) }
  return () => {
    if (before) data.value = before
  }
}

async function queueWrite(apply: () => Promise<unknown>, undo: () => void) {
  queueBusy.value = true
  error.value = null
  try {
    await apply()
    queueBusy.value = false
    await loadList()
  } catch (e) {
    undo()
    error.value = `Frontu se nepodařilo uložit: ${message(e)}`
  } finally {
    queueBusy.value = false
  }
}

/** The kanban reordered Připraveno (`shown`: its visible cards, maybe filtered). */
async function onReorder(shown: string[]) {
  const ready = tasks.value.filter((t) => kanbanColumn(t) === 'ready').map((t) => t.id)
  const order = mergeQueueOrder(ready, shown)
  const undo = optimistic((list) => {
    const byId = new Map(list.map((t) => [t.id, t]))
    const queued = order.map((id) => byId.get(id)).filter((t): t is (typeof list)[number] => !!t)
    const rest = list.filter((t) => !order.includes(t.id))
    return [...queued.map((t, i) => ({ ...t, queue_rank: i })), ...rest]
  })
  await queueWrite(() => setQueueOrder(order), undo)
}

/** Exclude a task from auto continue (Odloženo) or return it, from the kanban or the detail. */
async function onExclude(id: string, excluded: boolean) {
  const undo = optimistic((list) => list.map((t) => (t.id === id ? { ...t, auto_excluded: excluded } : t)))
  const before = detail.value
  if (before && before.task.id === id) detail.value = { ...before, task: { ...before.task, auto_excluded: excluded } }
  await queueWrite(
    async () => {
      await setAutoExcluded(id, excluded)
      if (taskId.value === id) await loadDetail(id)
    },
    () => {
      undo()
      if (before && detail.value?.task.id === id) detail.value = before
    },
  )
}

async function openRun() {
  const id = taskId.value
  if (!id) return
  run.value = { ...closedRun(), open: true, loading: true }
  try {
    const check = await fetchRunCheck(id)
    run.value = { ...run.value, check, loading: false }
  } catch (e) {
    run.value = { ...run.value, loading: false, error: flattenIssues(e) }
  }
}

async function onRunStart(input: RunInput & { force: boolean }) {
  const id = taskId.value
  if (!id) return
  const action = input.force ? 'force' : 'start'
  knownRuns = new Set((detail.value?.runs ?? []).map((r) => r.run_id))
  run.value = { ...run.value, busy: true, action, waiting: false, error: null, result: null }
  try {
    const { force, ...rest } = input
    const result = await startRun(id, { ...rest, note: input.note || undefined, force })
    // a started run opens its detail; `pending`: the run is still starting, the spinner
    // stays until live updates bring it and the dialog offers to open it
    if (result.run && !result.pending) {
      run.value = closedRun()
      window.location.hash = runHref(result.run.run_id)
      return
    }
    const waiting = result.pending && !result.run
    run.value = { ...run.value, busy: false, action: waiting ? action : null, waiting, result }
    await loadDetail(id)
  } catch (e) {
    run.value = { ...run.value, busy: false, action: null, waiting: false, error: flattenIssues(e) }
  }
}

/** Commit the backlog to base from the run dialog, then check the run again. */
async function onRunCommit() {
  const id = taskId.value
  if (!id) return
  run.value = { ...run.value, busy: true, action: 'commit', error: null }
  try {
    await commitBacklog()
    void backlogStatus.refresh()
    const check = await fetchRunCheck(id)
    run.value = { ...run.value, busy: false, action: null, check }
    await loadDetail(id)
  } catch (e) {
    run.value = { ...run.value, busy: false, action: null, error: flattenIssues(e) }
  }
}

function closeRun() {
  run.value = closedRun()
}

async function write<T>(key: string, run: () => Promise<T>): Promise<T | null> {
  busyAction.value = key
  writeError.value = null
  try {
    return await run()
  } catch (e) {
    writeError.value = flattenIssues(e)
    return null
  } finally {
    busyAction.value = null
  }
}

/** A write created a workflow: the config banner of the repo screen asks to commit it. */
function afterWorkflowWrite(result: WriteResult) {
  if (result.requires_config_commit) void configStatus.refresh()
}

async function onAdd(input: AddTaskInput | EditTaskInput) {
  const result = await write('add', () => addTask(input as AddTaskInput))
  if (result) {
    afterWorkflowWrite(result)
    await loadList()
    window.location.hash = taskHref(result.task.id)
  }
}

async function afterDetailWrite(result: WriteResult | null) {
  if (result) {
    afterWorkflowWrite(result)
    if (result.requires_config_commit) await loadList()
    if (taskId.value) await loadDetail(taskId.value)
  }
}

async function onEdit(input: EditTaskInput) {
  const id = taskId.value
  if (!id) return
  await afterDetailWrite(await write('edit', () => editTask(id, input)))
}

async function onLink(input: LinkInput) {
  const id = taskId.value
  if (!id) return
  await afterDetailWrite(await write(linkActionKey(input), () => linkTask(id, input)))
}

async function onAssign(workflow: string | null) {
  const id = taskId.value
  if (!id) return
  const input: EditTaskInput = workflow ? { workflow } : { clear_workflow: true }
  await afterDetailWrite(await write('assign', () => editTask(id, input)))
}

/** A switch in the tree was written: load the tree again. */
function reloadTree() {
  void loadList()
}

/** Project and step filter the loaded kanban. */
function onFilters(next: Filters) {
  filters.value = next
}

/** What a live event changed: backlog paths and tasks with changed runs or PRs. */
interface LiveChange {
  paths: string[]
  taskIds: string[]
  truncated: boolean
}

let deferred: LiveChange | null = null

function merge(a: LiveChange | null, b: LiveChange): LiveChange {
  if (!a) return b
  return {
    paths: [...a.paths, ...b.paths],
    taskIds: [...a.taskIds, ...b.taskIds],
    truncated: a.truncated || b.truncated,
  }
}

function writing(): boolean {
  return busy.value || queueBusy.value || run.value.busy || loading.value
}

/** Refresh only the parts of the open screen that the change touches, without a spinner. */
async function liveRefresh(change: LiveChange) {
  if (writing()) {
    deferred = merge(deferred, change)
    return
  }
  const key = routeKey.value
  try {
    if (isGraph.value) {
      const id = graphId.value
      const hit =
        id !== null &&
        (change.truncated ||
          touchesContainer(change.paths, id) ||
          change.taskIds.some((t) => t.startsWith(`${id}-`)))
      // the list too: the forms (steps of a new task) read it after the graph is left
      const [list, next, settings] = await Promise.all([
        fetchBacklog(),
        id && hit ? fetchGraph(id) : Promise.resolve(null),
        id && hit ? fetchContainer(id).catch(() => undefined) : Promise.resolve(undefined),
      ])
      if (routeKey.value !== key) return
      data.value = list
      if (next !== null) {
        graph.value = next
        if (settings !== undefined) setContainer(settings)
      }
      return
    }
    const id = taskId.value
    const taskHit =
      id !== null &&
      (change.truncated || touchesTask(change.paths, id) || change.taskIds.includes(id))
    const [list, task] = await Promise.all([
      fetchBacklog(),
      id && taskHit ? fetchTask(id) : Promise.resolve(null),
    ])
    if (routeKey.value !== key) return
    data.value = list
    if (id && task?.task && taskId.value === id) setDetail(id, task)
  } catch (e) {
    error.value = `Backlog se nepodařilo obnovit: ${message(e)}`
  }
}

function onFiles(event: LiveFilesEvent) {
  const relevant =
    event.areas.includes('backlog') ||
    (event.areas.includes('factory') && (event.truncated || touchesWorkflows(event.paths)))
  if (relevant) void liveRefresh({ paths: event.paths, taskIds: [], truncated: event.truncated })
}

function onTrace(event: LiveTraceEvent) {
  if (event.runs_changed) void liveRefresh({ paths: [], taskIds: event.task_ids, truncated: false })
}

useLive({ files: onFiles, trace: onTrace, resync: () => reload() })

watch(writing, (now) => {
  if (!now && deferred) {
    const change = deferred
    deferred = null
    void liveRefresh(change)
  }
})

function cancelNew() {
  window.location.hash = here('backlog')
}

watch(
  routeKey,
  (next, previous) => {
    if (next !== previous || next === '') {
      deferred = null
      newTaskReady.value = false
      selectedProject.value = ''
      setDetail(taskId.value ?? '', null)
      graph.value = null
      container.value = null
      containerError.value = null
      run.value = closedRun()
      reload()
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="backlog-view">
    <div class="view-head">
      <h1>Backlog</h1>
      <BackLink v-if="target" :href="here('backlog')" label="backlog" />
      <div class="head-actions">
        <a
          v-if="!target"
          :href="newContainerHref()"
          class="button"
          data-test="new-project"
        >
          <Plus :size="16" /> Nový {{ levelNoun(level.top.value) }}
        </a>
        <a
          v-if="!target && listChildLevel"
          :href="newStepHref()"
          class="button"
          data-test="new-step"
        >
          <Plus :size="16" /> Nový {{ levelNoun(listChildLevel) }}
        </a>
        <a
          v-if="isGraph && graph && graphChildLevel"
          :href="newContainerHref(graph.container.id)"
          class="button"
          data-test="new-step"
        >
          <Plus :size="16" /> Nový {{ levelNoun(graphChildLevel) }}
        </a>
        <a v-if="!isNew" :href="newTaskHref(graphStep)" class="button" data-test="new-task">
          <Plus :size="16" /> Nový {{ levelNoun(level.task.value) }}
        </a>
        <button type="button" class="button" data-test="refresh" :disabled="loading" @click="reload">
          <RefreshCw :size="16" :class="{ spin: loading }" /> Obnovit
        </button>
      </div>
    </div>
    <p v-if="error" class="error-bar" data-test="error">
      {{ error }}
      <button v-if="isDbBusyText(error)" type="button" class="retry" data-test="retry" @click="reload">
        Zkusit znovu
      </button>
    </p>

    <template v-if="isNew">
      <TaskForm
        v-if="newTaskReady"
        mode="add"
        :steps="steps"
        :task-ids="Object.keys(names)"
        :initial-step="newTaskStep"
        :workflows="workflows"
        :busy="busy"
        :pending="busyAction === 'add'"
        :error="writeError"
        @submit="onAdd"
        @cancel="cancelNew"
      />
      <p v-else-if="loading" class="faint" data-test="new-task-loading">Načítám…</p>
    </template>
    <template v-else-if="isNewContainer">
      <template v-if="isNewStep">
        <p v-if="loading" class="faint" data-test="new-step-loading">Načítám…</p>
        <template v-else-if="data && !error">
          <p v-if="!listChildLevel" class="error-bar" data-test="no-child-level">
            {{ levelLabel(level.top.value) }} obsahuje jen {{ levelNoun(level.task.value) }}y.
          </p>
          <label v-else-if="projects.length" class="step-project">
            {{ levelLabel(level.top.value) }}
            <SelectMenu
              data-test="step-project"
              :label="levelLabel(level.top.value)"
              :model-value="selectedProject"
              :options="projectChoices"
              :placeholder="`Vyber ${levelNoun(level.top.value)}`"
              :disabled="busy"
              @update:model-value="selectedProject = $event"
            />
          </label>
          <p v-else data-test="new-step-empty">
            Nejprve založ {{ levelNoun(level.top.value) }}.
            <a :href="newContainerHref()">Nový {{ levelNoun(level.top.value) }}</a>
          </p>
        </template>
      </template>
      <ContainerForm
        v-if="newLevel && (!isNewStep || (newParent && listChildLevel))"
        :key="newParent ?? ''"
        :level="newLevel"
        :parent="newParent"
        :siblings="newSiblings"
        :parent-title="newParent ? (names[newParent]?.title ?? null) : null"
        :busy="busy"
        :pending="busyAction === 'add-container'"
        :error="writeError"
        @submit="onAddContainer"
        @cancel="cancelNewContainer"
      />
      <p v-else-if="data && !isNewStep" class="error-bar" data-test="no-child-level">
        {{ newParent }} obsahuje jen {{ levelNoun(level.task.value) }}y.
      </p>
    </template>
    <template v-else-if="taskId">
      <TaskDetail
        v-if="shownDetail"
        :detail="shownDetail"
        :workflows="workflows"
        :busy="busy"
        :action="busyAction"
        :error="writeError"
        :run="run"
        :queue-busy="queueBusy"
        @edit="onEdit"
        @exclude="onExclude"
        @link="onLink"
        @assign-workflow="onAssign"
        @open-run="openRun"
        @run-start="onRunStart"
        @run-cancel="closeRun"
        @run-commit="onRunCommit"
      />
      <p v-else-if="loading" class="faint" data-test="detail-loading">
        <span class="mono" data-test="loading-id">{{ taskId }}</span> · Načítám…
      </p>
    </template>
    <template v-else-if="isGraph">
      <section v-if="graph" class="graph-view" :data-container="graph.container.id">
        <div class="graph-head">
          <span class="level" data-test="graph-level">{{ levelLabel(graph.container.level) }}</span>
          <CodeTip :code="graph.container.id">
            <span class="mono dim" data-test="graph-id">{{ graph.container.id }}</span>
          </CodeTip>
          <h2 data-test="graph-title">{{ graph.container.title }}</h2>
          <label class="check graph-hide-done">
            <input
              type="checkbox"
              data-test="hide-done"
              :checked="hideDone"
              @change="onHideDone(($event.target as HTMLInputElement).checked)"
            />
            Skrýt hotové
          </label>
        </div>
        <DependencyGraph :graph="shownGraph ?? graph" />
        <ContainerSettings
          v-if="container"
          :key="settingsKey"
          :container="container.container"
          :editable-keys="container.editable_keys"
          :workflows="workflows"
          :busy="busy"
          :pending="busyAction === 'settings'"
          :error="writeError"
          @save="onSaveSettings"
        />
        <p v-else-if="containerError" class="error-bar" data-test="settings-error">{{ containerError }}</p>
      </section>
      <p v-else-if="loading" class="faint">Načítám…</p>
    </template>
    <template v-else>
      <div v-if="issues.length" data-test="problems">
        <IssueList :message="problemsText" :issues="issues" />
      </div>
      <BacklogFilters
        :filters="filters"
        :mode="mode"
        :levels="levels"
        :projects="projects"
        :steps="steps"
        :hide-done="hideDone"
        @update:filters="onFilters"
        @update:hide-done="onHideDone"
        @update:mode="mode = $event"
      />
      <template v-if="data">
        <KanbanBoard
          v-if="mode === 'kanban'"
          :tasks="kanbanTasks"
          :states="kanbanStates"
          :busy="queueBusy"
          @reorder="onReorder"
          @exclude="onExclude"
        />
        <BacklogTree
          v-else
          :items="treeItems"
          :levels="levels"
          :filtered="treeFiltered"
          @changed="reloadTree"
          @clear-filter="onHideDone(false)"
        />
      </template>
      <p v-else-if="loading" class="faint" data-test="list-loading">Načítám…</p>
    </template>
  </section>
</template>

<style scoped>
.backlog-view {
  padding: 28px;
  max-width: 1600px;
  margin: 0 auto;
}

.view-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

.head-actions {
  display: flex;
  gap: 10px;
  margin-left: auto;
}

.step-project {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 720px;
  margin-bottom: 12px;
  color: var(--dim);
}

.button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}

.graph-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.graph-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.graph-head h2 {
  margin: 0;
  font-size: 22px;
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--dim);
  cursor: pointer;
}

.graph-hide-done {
  margin-left: auto;
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

.mono {
  font-family: var(--mono);
  font-size: 14px;
}

[data-test='problems'] {
  margin-bottom: 12px;
}
</style>

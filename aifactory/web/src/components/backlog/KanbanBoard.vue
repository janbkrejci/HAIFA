<script setup lang="ts">
// The kanban of the Backlog screen. The Připraveno column is the auto-continue queue: its
// order changes by drag and drop or the ↑/↓ buttons (`reorder` with the whole new order).
// Odloženo holds tasks excluded from auto continue; a card moves there and back by drag and
// drop or its switch (`exclude`).
import { computed, ref } from 'vue'
import { ArrowDown, ArrowUp, PauseCircle, PlayCircle } from 'lucide-vue-next'
import Tooltip from '@/components/ui/Tooltip.vue'
import {
  COLUMN_LABELS,
  DEFERRABLE_STATES,
  STATE_TOOLTIPS,
  kanbanColumn,
  kanbanColumns,
  type BoardState,
  type KanbanColumn,
  type TaskNode,
} from '@/lib/backlog'
import { taskHref } from '@/lib/router'

const props = defineProps<{
  tasks: TaskNode[]
  states: readonly BoardState[]
  /** A queue write is running: the reorder and exclude controls wait. */
  busy?: boolean
}>()

const emit = defineEmits<{
  reorder: [ids: string[]]
  exclude: [id: string, excluded: boolean]
}>()

const COLUMN_TOOLTIPS: Partial<Record<KanbanColumn, string>> = {
  ...STATE_TOOLTIPS,
  deferred: 'Tasky vyloučené z auto continue. Auto continue je nespustí, ručně je spustit jde.',
}

const columns = computed(() =>
  kanbanColumns(props.states).map((column) => ({
    column,
    tasks: props.tasks.filter((t) => kanbanColumn(t) === column),
  })),
)

const readyIds = computed(() => props.tasks.filter((t) => kanbanColumn(t) === 'ready').map((t) => t.id))

function canExclude(task: TaskNode): boolean {
  return DEFERRABLE_STATES.includes(task.board_state)
}

function canDrag(task: TaskNode): boolean {
  const column = kanbanColumn(task)
  return column === 'ready' || column === 'deferred'
}

function move(id: string, by: number) {
  const ids = [...readyIds.value]
  const from = ids.indexOf(id)
  const to = from + by
  if (from < 0 || to < 0 || to >= ids.length) return
  ids.splice(from, 1)
  ids.splice(to, 0, id)
  emit('reorder', ids)
}

function toggleExclude(task: TaskNode) {
  emit('exclude', task.id, !task.auto_excluded)
}

// ── drag and drop ───────────────────────────────────────────────────────────
const dragged = ref<{ id: string; from: KanbanColumn } | null>(null)
/** The column under the dragged card (highlighted as a drop target). */
const over = ref<KanbanColumn | null>(null)

function isTarget(column: KanbanColumn): boolean {
  if (!dragged.value) return false
  if (column === 'ready') return true
  return column === 'deferred' && dragged.value.from !== 'deferred'
}

function onDragStart(event: DragEvent, task: TaskNode) {
  if (props.busy || !canDrag(task)) {
    event.preventDefault()
    return
  }
  dragged.value = { id: task.id, from: kanbanColumn(task) }
  event.dataTransfer?.setData('text/plain', task.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDragEnd() {
  dragged.value = null
  over.value = null
}

function onDragOver(event: DragEvent, column: KanbanColumn) {
  if (!isTarget(column)) return
  event.preventDefault()
  over.value = column
}

/** A drop on a column (`beforeId`: dropped on that card of Připraveno). */
function onDrop(event: DragEvent, column: KanbanColumn, beforeId: string | null = null) {
  const drag = dragged.value
  onDragEnd()
  if (!drag || props.busy) return
  event.preventDefault()
  if (column === 'deferred') {
    if (drag.from !== 'deferred') emit('exclude', drag.id, true)
    return
  }
  if (column !== 'ready') return
  if (drag.from !== 'ready') {
    emit('exclude', drag.id, false)
    return
  }
  if (beforeId === drag.id) return
  const ids = readyIds.value.filter((id) => id !== drag.id)
  const at = beforeId ? ids.indexOf(beforeId) : -1
  ids.splice(at < 0 ? ids.length : at, 0, drag.id)
  if (ids.join('\n') !== readyIds.value.join('\n')) emit('reorder', ids)
}
</script>

<template>
  <p class="queue-help faint" data-test="queue-help">
    Auto continue bere tasky ze sloupce Připraveno shora dolů. Odložené tasky nespustí, ručně je spustit jde.
  </p>
  <div
    class="board"
    data-test="kanban"
    :style="{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(170px, 1fr))` }"
  >
    <section
      v-for="col in columns"
      :key="col.column"
      class="column"
      :class="{ target: dragged && isTarget(col.column), over: over === col.column }"
      :data-column="col.column"
      @dragover="onDragOver($event, col.column)"
      @dragleave="over === col.column && (over = null)"
      @drop="onDrop($event, col.column)"
    >
      <h2>
        <Tooltip v-if="COLUMN_TOOLTIPS[col.column]" :text="COLUMN_TOOLTIPS[col.column] ?? ''">
          <span class="label hint" tabindex="0" data-test="column-tip">{{ COLUMN_LABELS[col.column] ?? col.column }}</span>
        </Tooltip>
        <span v-else class="label">{{ COLUMN_LABELS[col.column] ?? col.column }}</span>
        <span class="count" data-test="count">{{ col.tasks.length }}</span>
      </h2>
      <p v-if="!col.tasks.length" class="faint empty">—</p>
      <div
        v-for="(task, index) in col.tasks"
        :key="task.path"
        class="item"
        :class="{ dragging: dragged?.id === task.id }"
        :data-item="task.id"
        :draggable="canDrag(task) && !busy"
        @dragstart="onDragStart($event, task)"
        @dragend="onDragEnd"
        @drop.stop="onDrop($event, col.column, col.column === 'ready' ? task.id : null)"
      >
        <a class="card" :href="taskHref(task.id)" :data-card="task.id" draggable="false">
          <span class="id">
            <span v-if="col.column === 'ready'" class="rank" data-test="queue-rank">{{ index + 1 }}.</span>
            {{ task.id }}
          </span>
          <span class="title">{{ task.title }}</span>
          <span class="meta">
            <span :class="{ faint: !task.workflow }">{{ task.workflow ?? 'bez workflow' }}</span>
          </span>
          <span v-if="task.invalid" class="warn" data-test="invalid">neplatný status</span>
        </a>
        <div v-if="canExclude(task)" class="tools">
          <template v-if="col.column === 'ready'">
            <button
              type="button"
              class="icon"
              data-test="move-up"
              aria-label="Posunout výš"
              :disabled="busy || index === 0"
              @click="move(task.id, -1)"
            >
              <ArrowUp :size="14" />
            </button>
            <button
              type="button"
              class="icon"
              data-test="move-down"
              aria-label="Posunout níž"
              :disabled="busy || index === col.tasks.length - 1"
              @click="move(task.id, 1)"
            >
              <ArrowDown :size="14" />
            </button>
          </template>
          <Tooltip :text="task.auto_excluded ? 'Vrátit do auto continue' : 'Vyloučit z auto continue'">
            <button
              type="button"
              class="icon"
              data-test="exclude-toggle"
              :aria-label="task.auto_excluded ? 'Vrátit do auto continue' : 'Vyloučit z auto continue'"
              :aria-pressed="!!task.auto_excluded"
              :disabled="busy"
              @click="toggleExclude(task)"
            >
              <PlayCircle v-if="task.auto_excluded" :size="14" />
              <PauseCircle v-else :size="14" />
            </button>
          </Tooltip>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.queue-help {
  margin: 0 0 10px;
  font-size: 14px;
}

.board {
  display: grid;
  gap: 12px;
  overflow-x: auto;
}

.column {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
  min-height: 120px;
}

.column.target {
  border-style: dashed;
}

.column.over {
  border-color: var(--blue);
}

h2 {
  display: flex;
  justify-content: space-between;
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--dim);
}

.hint {
  cursor: help;
}

.count {
  color: var(--faint);
}

.empty {
  margin: 0;
  text-align: center;
}

.item {
  margin-bottom: 8px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--panel);
}

.item[draggable='true'] {
  cursor: grab;
}

.item:hover {
  border-color: var(--border);
}

.item.dragging {
  opacity: 0.5;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  color: var(--text);
  text-decoration: none;
}

.id {
  font-family: var(--mono);
  font-size: 13px;
  color: var(--dim);
}

.rank {
  color: var(--blue);
  font-weight: 600;
}

.meta {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-size: 13px;
}

.warn {
  color: var(--amber);
  font-size: 13px;
}

.tools {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 0 6px 6px;
}

button.icon {
  display: inline-flex;
  align-items: center;
  padding: 2px 4px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--dim);
  cursor: pointer;
}

button.icon:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>

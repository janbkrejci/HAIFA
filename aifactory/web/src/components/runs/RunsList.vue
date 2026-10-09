<script setup lang="ts">
import { Archive, ArchiveRestore, Trash2 } from 'lucide-vue-next'
import { fmtCost, fmtDuration, fmtTime, fmtTokens } from '@/lib/format'
import { runHref } from '@/lib/router'
import { isFinished, shownState, startedByLabel, startedByTip, type RunSummary } from '@/lib/runs'
import Tooltip from '@/components/ui/Tooltip.vue'
import PhaseDots from './PhaseDots.vue'
import StatusChip from './StatusChip.vue'

withDefaults(
  defineProps<{
    runs: RunSummary[]
    /** The list has arrived at least once (until then no empty state). */
    ready?: boolean
    loading?: boolean
    /** The archived view: only archived runs; otherwise only the active ones. */
    archived?: boolean
    /** An archive or delete request is on its way: the actions are disabled. */
    busy?: boolean
  }>(),
  { ready: true, loading: false, archived: false, busy: false },
)

const emit = defineEmits<{
  'update:archived': [value: boolean]
  archive: [runId: string]
  unarchive: [runId: string]
  delete: [runId: string]
  'archive-finished': []
  'delete-archived': []
}>()

/** A click anywhere on a row opens the run, except on a link or a button inside it. */
function openRun(event: MouseEvent, run: RunSummary) {
  const target = event.target as Element | null
  if (target?.closest('a, button')) return
  window.location.hash = runHref(run.run_id)
}
</script>

<template>
  <div class="runs-list">
    <div class="filters">
      <div class="view-switch" role="group" aria-label="Zobrazení">
        <button
          type="button"
          data-test="view-active"
          :class="{ on: !archived }"
          :aria-pressed="!archived"
          @click="emit('update:archived', false)"
        >
          Aktivní
        </button>
        <button
          type="button"
          data-test="view-archived"
          :class="{ on: archived }"
          :aria-pressed="archived"
          @click="emit('update:archived', true)"
        >
          Archivované
        </button>
      </div>
      <button
        v-if="!archived"
        type="button"
        class="bulk"
        data-test="archive-finished"
        :disabled="busy"
        @click="emit('archive-finished')"
      >
        <Archive :size="15" /> Archivovat dokončené
      </button>
      <button
        v-else
        type="button"
        class="bulk danger"
        data-test="delete-archived"
        :disabled="busy || !runs.length"
        @click="emit('delete-archived')"
      >
        <Trash2 :size="15" /> Vymazat všechny
      </button>
    </div>

    <template v-if="!ready">
      <p v-if="loading" class="faint" data-test="list-loading">Načítám…</p>
    </template>
    <p v-else-if="!runs.length" class="empty-state" data-test="no-runs">
      {{ archived ? 'Žádné archivované běhy' : 'Žádné běhy' }}
    </p>
    <table v-else class="table">
      <thead>
        <tr>
          <th>Task</th>
          <th>Workflow</th>
          <th>Stav</th>
          <th>Začátek</th>
          <th>Spustil</th>
          <th class="num">Doba</th>
          <th class="num">Tokeny</th>
          <th class="num">Náklady</th>
          <th>PR</th>
          <th>Fáze</th>
          <th class="actions"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="run in runs"
          :key="run.run_id"
          :data-run="run.run_id"
          class="run-row"
          @click="openRun($event, run)"
        >
          <td>
            <a :href="runHref(run.run_id)" class="task-link" data-test="task-label"
              ><span class="task-id">{{ run.task_id }}</span
              ><span v-if="run.task_title" class="dim">{{ ' ' + run.task_title }}</span></a
            >
          </td>
          <td>{{ run.workflow ?? '—' }}</td>
          <td><StatusChip :status="shownState(run)" /></td>
          <td class="nowrap">{{ fmtTime(run.started_at) }}</td>
          <td class="nowrap">
            <Tooltip :text="startedByTip(run.started_by)">
              <span class="started-by" :class="{ faint: !run.started_by }" tabindex="0" data-col="started-by">
                {{ startedByLabel(run.started_by) }}
              </span>
            </Tooltip>
          </td>
          <td class="num" data-col="duration">{{ fmtDuration(run.duration_s) }}</td>
          <td class="num" data-col="tokens">{{ fmtTokens(run.tokens) }}</td>
          <td class="num" data-col="cost">{{ fmtCost(run.cost) }}</td>
          <td>
            <a v-if="run.pr" :href="run.pr.url" target="_blank" rel="noopener" data-col="pr">
              #{{ run.pr.pr_id }}
            </a>
            <span v-else class="faint">—</span>
          </td>
          <td><PhaseDots :phases="run.phases ?? []" /></td>
          <td class="actions">
            <template v-if="archived">
              <Tooltip text="Vrátit z archivu">
                <button
                  type="button"
                  class="icon"
                  data-test="unarchive"
                  aria-label="Vrátit z archivu"
                  :disabled="busy"
                  @click="emit('unarchive', run.run_id)"
                >
                  <ArchiveRestore :size="16" />
                </button>
              </Tooltip>
              <Tooltip text="Smazat z databáze">
                <button
                  type="button"
                  class="icon danger"
                  data-test="delete"
                  aria-label="Smazat z databáze"
                  :disabled="busy"
                  @click="emit('delete', run.run_id)"
                >
                  <Trash2 :size="16" />
                </button>
              </Tooltip>
            </template>
            <Tooltip v-else-if="isFinished(run)" text="Archivovat">
              <button
                type="button"
                class="icon"
                data-test="archive"
                aria-label="Archivovat"
                :disabled="busy"
                @click="emit('archive', run.run_id)"
              >
                <Archive :size="16" />
              </button>
            </Tooltip>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 14px;
  color: var(--dim);
}

.view-switch {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.view-switch button {
  padding: 5px 12px;
  border: 0;
  background: transparent;
  color: var(--dim);
  font: inherit;
  cursor: pointer;
}

.view-switch button + button {
  border-left: 1px solid var(--border);
}

.view-switch button.on {
  background: var(--panel-2);
  color: var(--text);
  font-weight: 700;
}

.bulk {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.bulk.danger {
  border-color: rgba(255, 111, 103, 0.55);
  color: var(--red);
}

.bulk:disabled,
.icon:disabled {
  opacity: 0.5;
  cursor: default;
}

.run-row {
  cursor: pointer;
}

td.actions {
  width: 1%;
  white-space: nowrap;
  text-align: right;
}

.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--dim);
  cursor: pointer;
}

.icon:hover:not(:disabled) {
  background: var(--panel);
  color: var(--text);
}

.icon.danger:hover:not(:disabled) {
  color: var(--red);
}

.table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-soft);
  text-align: left;
  vertical-align: middle;
}

th {
  color: var(--faint);
  font-weight: 600;
  font-size: 14px;
}

.num {
  text-align: right;
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}

.nowrap {
  white-space: nowrap;
}

.task-id {
  font-family: var(--mono);
  color: var(--text);
}

tbody tr:hover {
  background: var(--panel-2);
}
</style>

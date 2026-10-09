<script setup lang="ts">
import { computed } from 'vue'
import { fmtCost, fmtTime, fmtTokens } from '@/lib/format'
import { here, reviewHref, runHref } from '@/lib/router'
import { doneLabel, mergedByAuto, type ReviewDonePr, type ReviewList, type ReviewPr } from '@/lib/review'
import MergeabilityChip from './MergeabilityChip.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import CodeTip from '@/components/ui/CodeTip.vue'
import { levelLabel } from '@/lib/backlog'
import { useLevels } from '@/lib/names'

const props = withDefaults(
  defineProps<{
    list: ReviewList
    /** The list has arrived at least once (until then no empty state). */
    ready?: boolean
    loading?: boolean
    /** Show the "Hotové" section with merged and closed PRs. */
    showDone?: boolean
  }>(),
  { ready: true, loading: false, showDone: false },
)

const prs = computed<ReviewPr[]>(() => (Array.isArray(props.list.prs) ? props.list.prs : []))
const awaiting = computed(() => prs.value.filter((p) => p.awaiting_review))
const other = computed(() => prs.value.filter((p) => !p.awaiting_review))

const sections = computed(() => [
  { key: 'awaiting', title: 'Čeká na review', items: awaiting.value },
  { key: 'other', title: 'Ostatní otevřené PR', items: other.value },
])

/** Merged and closed PRs, newest first. */
const done = computed<ReviewDonePr[]>(() => {
  const items = Array.isArray(props.list.done) ? [...props.list.done] : []
  return items.sort((a, b) => (b.done_at ?? '').localeCompare(a.done_at ?? ''))
})

const level = useLevels()
/** The project column is named by the top level of `levels` (Projekt, Modul, …). */
const projectLabel = computed(() => {
  const levels = Array.isArray(props.list.levels) ? props.list.levels : []
  return levelLabel(levels[0] ?? level.top.value)
})
const taskLabel = computed(() => levelLabel(level.task.value))

function isLocal(url: string): boolean {
  return url.startsWith('local:')
}
</script>

<template>
  <div class="review-list">
    <template v-if="!ready">
      <p v-if="loading" class="faint" data-test="list-loading">Načítám…</p>
    </template>
    <p v-else-if="!prs.length" class="empty-state" data-test="no-prs">
      Žádné PR ke schválení. Spusť task v <a :href="here('backlog')" data-test="no-prs-backlog">Backlogu</a>
      nebo sleduj <a :href="here('runs')" data-test="no-prs-runs">běžící běhy</a>.
    </p>
    <template v-else>
      <section v-for="s in sections" :key="s.key" class="group" :data-test="s.key">
        <h2>{{ s.title }} <span class="dim">({{ s.items.length }})</span></h2>
        <p v-if="!s.items.length" class="faint">Nic</p>
        <table v-else class="table">
          <thead>
            <tr>
              <th>{{ taskLabel }}</th>
              <th data-test="project-col">{{ projectLabel }}</th>
              <th>Mergeabilita</th>
              <th>Běh</th>
              <th class="num">Náklady</th>
              <th class="num">Tokeny</th>
              <th>PR</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in s.items" :key="p.task_id" :data-pr="p.task_id">
              <td>
                <a :href="reviewHref(p.task_id)" class="task-link" data-test="task-label"
                  ><span class="task-id">{{ p.task_id }}</span
                  ><span v-if="p.task_title" class="dim">{{ ' ' + p.task_title }}</span></a
                >
              </td>
              <td data-col="project">
              <CodeTip v-if="p.project_id" :code="p.project_id" />
              <template v-else>—</template>
            </td>
              <td>
                <MergeabilityChip :value="p.mergeability" />
                <Tooltip v-if="p.pr.auto_merge_error" :text="p.pr.auto_merge_error">
                  <span class="auto-note" data-test="auto-merge-error" tabindex="0"
                    >auto-merge nesloučil</span
                  >
                </Tooltip>
              </td>
              <td data-col="run">
                <a v-if="p.running_run" :href="runHref(p.running_run.run_id)">
                  běží {{ p.running_run.workflow ?? '' }}
                </a>
                <span v-else class="faint">—</span>
              </td>
              <td class="num" data-col="cost">{{ fmtCost(p.cost) }}</td>
              <td class="num" data-col="tokens">{{ fmtTokens(p.tokens) }}</td>
              <td>
                <span v-if="isLocal(p.pr.url)" class="mono" data-col="pr">{{ p.pr.url }}</span>
                <a v-else :href="p.pr.url" target="_blank" rel="noopener" data-col="pr">
                  #{{ p.pr.pr_id }}
                </a>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
    <section v-if="ready && showDone" class="group" data-test="done">
      <h2>Hotové <span class="dim">({{ done.length }})</span></h2>
      <p v-if="!done.length" class="faint">Nic</p>
      <table v-else class="table">
        <thead>
          <tr>
            <th>{{ taskLabel }}</th>
            <th data-test="project-col">{{ projectLabel }}</th>
            <th>Stav</th>
            <th>Datum</th>
            <th class="num">Náklady</th>
            <th>PR</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in done" :key="p.pr.branch" :data-done-pr="p.task_id">
            <td>
              <a :href="reviewHref(p.task_id)" class="task-link" data-test="task-label"
                ><span class="task-id">{{ p.task_id }}</span
                ><span v-if="p.task_title" class="dim">{{ ' ' + p.task_title }}</span></a
              >
            </td>
            <td data-col="project">
              <CodeTip v-if="p.project_id" :code="p.project_id" />
              <template v-else>—</template>
            </td>
            <td>
              <span class="chip done-chip" :data-state="p.provider_state" data-col="state">{{
                doneLabel(p.provider_state)
              }}</span>
              <span v-if="mergedByAuto(p.pr)" class="chip auto-chip" data-test="merged-by-auto"
                >auto-merge</span
              >
            </td>
            <td data-col="done-at">{{ fmtTime(p.done_at) }}</td>
            <td class="num" data-col="cost">{{ fmtCost(p.cost) }}</td>
            <td>
              <span v-if="isLocal(p.pr.url)" class="mono" data-col="pr">{{ p.pr.url }}</span>
              <a v-else :href="p.pr.url" target="_blank" rel="noopener" data-col="pr">
                #{{ p.pr.pr_id }}
              </a>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.group {
  margin-bottom: 24px;
}

h2 {
  font-size: 17px;
  margin: 0 0 8px;
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

.task-id,
.mono {
  font-family: var(--mono);
  color: var(--text);
}

.done-chip {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
  color: var(--dim);
}

.auto-chip {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  border: 1px solid rgba(90, 210, 221, 0.45);
  border-radius: 999px;
  font-size: 13px;
  color: var(--cyan);
}

.auto-note {
  margin-left: 6px;
  font-size: 13px;
  color: var(--amber);
}

.done-chip[data-state='merged'] {
  color: var(--green);
  border-color: rgba(74, 222, 128, 0.45);
}
</style>

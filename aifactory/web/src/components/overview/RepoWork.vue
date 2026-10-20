<script setup lang="ts">
import { computed } from 'vue'
import type { OverviewRepo } from '@/lib/api'
import { activeRuns, automergePrs, failedRows, projectSections, reviewLink, runLink, runningKey, runningLink, stateClass, taskSummary } from '@/lib/overview'
import { fmtAge, fmtCost, fmtElapsed, ts } from '@/lib/format'

const props = withDefaults(defineProps<{ repo: OverviewRepo; now: number; byProject?: boolean }>(), { byProject: false })
const grouped = computed(() => props.byProject && (props.repo.projects?.length ?? 0) > 1)
const sections = computed(() => grouped.value ? projectSections(props.repo) : [{ id: null, title: '', repo: props.repo }])
function since(iso: string | null | undefined): number | null {
  const t = ts(iso)
  return Number.isFinite(t) ? Math.max(0, (props.now - t) / 1000) : null
}
function reviewAge(opened: string | null, ageS: number | null): string {
  return fmtAge(since(opened) ?? ageS)
}
</script>

<template>
  <div v-for="section in sections" :key="section.id ?? ''" class="work-section" :class="{ 'project-section': grouped }" :data-test="grouped ? 'project-section' : undefined" :data-project="section.id">
    <template v-if="grouped">
      <h3 class="project-name"><span v-if="section.id" class="project-code mono">{{ section.id }}</span><span>{{ section.title }}</span></h3>
      <div v-if="taskSummary(section.repo).length" class="tasks" data-test="task-summary">
        <span v-for="item in taskSummary(section.repo)" :key="item.state" class="chip state-chip" :class="stateClass(item.state)" data-test="task-summary-item" :data-state="item.state">{{ item.label }} <b>{{ item.count }}</b></span>
      </div>
    </template>
    <section v-if="activeRuns(section.repo).length" class="group">
      <h3>Běží</h3>
      <a
        v-for="run in activeRuns(section.repo)"
        :key="runningKey(run)"
        :href="runningLink(repo, run)"
        class="row"
        data-test="row-running"
        :data-run="run.run_id"
        :data-operation="run.operation_id"
      >
        <span class="task mono">{{ run.task_id }}</span>
        <span class="title">{{ run.task_title ?? '' }}</span>
        <span class="meta">{{ run.workflow ?? '—' }}</span>
        <span class="meta" data-test="row-phase">
          <template v-if="run.phase">{{ run.phase.name }}<template v-if="run.phase.attempt"> · pokus {{ run.phase.attempt }}</template></template>
          <template v-else>—</template>
        </span>
        <span class="meta mono" data-test="row-elapsed">{{ fmtElapsed(since(run.started_at)) }}</span>
        <span class="meta mono" data-test="row-cost">{{ fmtCost(run.cost) }}</span>
      </a>
    </section>

    <section v-if="section.repo.review.length" class="group">
      <h3>Čeká na review</h3>
      <a
        v-for="pr in section.repo.review"
        :key="pr.task_id"
        :href="reviewLink(repo, pr.task_id)"
        class="row"
        data-test="row-review"
        :data-task="pr.task_id"
      >
        <span class="task mono">{{ pr.task_id }}</span>
        <span class="title">{{ pr.task_title ?? '' }}</span>
        <span class="meta mono">{{ pr.pr_id ? `PR #${pr.pr_id}` : 'PR' }}</span>
        <span class="meta" data-test="row-age">{{ reviewAge(pr.opened_at, pr.age_s) }}</span>
        <span class="meta faint">podle trace</span>
      </a>
    </section>

    <section v-if="automergePrs(section.repo).length" class="group" data-test="automerge">
      <h3>Čeká na automerge PR</h3>
      <a
        v-for="pr in automergePrs(section.repo)"
        :key="pr.task_id"
        :href="reviewLink(repo, pr.task_id)"
        class="row"
        data-test="row-automerge"
        :data-task="pr.task_id"
      >
        <span class="task mono">{{ pr.task_id }}</span>
        <span class="title">{{ pr.task_title ?? '' }}</span>
        <span class="meta mono">{{ pr.pr_id ? `PR #${pr.pr_id}` : 'PR' }}</span>
        <span class="meta" data-test="row-age">{{ reviewAge(pr.opened_at, pr.age_s) }}</span>
        <span class="meta faint">podle trace</span>
      </a>
    </section>

    <slot v-if="!grouped" />

    <section v-if="failedRows(section.repo).length" class="group">
      <h3>Selhalo</h3>
      <a
        v-for="row in failedRows(section.repo)"
        :key="row.run_id"
        :href="runLink(repo, row.run_id)"
        class="row failed"
        data-test="row-failed"
        :data-run="row.run_id"
      >
        <span class="task mono">{{ row.task_id }}</span>
        <span class="title">{{ row.task_title ?? '' }}</span>
        <span class="error" data-test="row-error">{{ row.label ?? row.error ?? 'bez chyby' }}</span>
      </a>
    </section>

  </div>
  <slot v-if="grouped" />
</template>

<style scoped>
.work-section { display: flex; flex-direction: column; gap: 10px; }
.work-section:empty { display: none; }
.project-section { border-top: 1px solid var(--border); padding-top: 8px; }
.project-name { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; color: var(--text); text-transform: none; font-size: 15px; }
.project-code { color: var(--dim); font-size: 13px; font-weight: 400; }
.tasks { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; font-size: 13px; }
.chip { padding: 1px 8px; border-radius: 999px; }
.group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

h3 {
  margin: 0 0 2px;
  color: var(--dim);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 5px 8px;
  border-radius: 6px;
  color: var(--text);
  min-width: 0;
}

.row:hover {
  background: rgba(108, 182, 255, 0.12);
}

.task {
  flex: none;
  color: var(--blue);
}

.title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  flex: none;
  color: var(--dim);
  font-size: 14px;
}

.faint {
  color: var(--faint);
}

.error {
  flex: 2;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--red);
  font-size: 14px;
}

</style>

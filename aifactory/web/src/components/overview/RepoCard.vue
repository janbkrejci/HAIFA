<script setup lang="ts">
// A repo card of the overview: what runs, waits for review and failed, its configuration
// problems and the newest activity. Every row is a link to the run, the review or the settings.
import { computed } from 'vue'
import { Trash2 } from 'lucide-vue-next'
import type { OverviewRepo } from '@/lib/api'
import { fmtAge, fmtCost, fmtElapsed, fmtTime, ts } from '@/lib/format'
import { activeRuns, failedRows, problems, reviewLink, runLink } from '@/lib/overview'
import { repoHref } from '@/lib/router'

const props = withDefaults(defineProps<{ repo: OverviewRepo; now: number; removing?: boolean }>(), {
  removing: false,
})
const emit = defineEmits<{ remove: [repo: OverviewRepo] }>()

const running = computed(() => activeRuns(props.repo))
const failed = computed(() => failedRows(props.repo))
const configProblems = computed(() => problems(props.repo).filter((p) => p.href !== null))
const stateProblems = computed(() => problems(props.repo).filter((p) => p.href === null))

/** Seconds from `iso` to now (the browser's clock), null for a missing timestamp. */
function since(iso: string | null | undefined): number | null {
  const t = ts(iso)
  return Number.isFinite(t) ? Math.max(0, (props.now - t) / 1000) : null
}

function reviewAge(opened: string | null, ageS: number | null): string {
  return fmtAge(since(opened) ?? ageS)
}
</script>

<template>
  <article class="repo-card" data-test="overview-card" :data-repo="repo.id">
    <header class="card-head">
      <a :href="repoHref(repo.id, 'backlog')" class="repo-name" data-test="card-name">{{ repo.name }}</a>
      <span class="repo-path mono">{{ repo.path }}</span>
    </header>

    <p v-for="p in stateProblems" :key="p.kind" class="state-problem" :data-test="`state-${p.kind}`">{{ p.text }}</p>
    <div class="card-actions">
      <button type="button" class="remove" :disabled="removing" data-test="card-remove" @click="emit('remove', repo)">
        <Trash2 :size="14" aria-hidden="true" /> Odebrat z dashboardu
      </button>
    </div>

    <section v-if="running.length" class="group">
      <h3>Běží</h3>
      <a
        v-for="run in running"
        :key="run.run_id"
        :href="runLink(repo, run.run_id)"
        class="row"
        data-test="row-running"
        :data-run="run.run_id"
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

    <section v-if="repo.review.length" class="group">
      <h3>Čeká na review</h3>
      <a
        v-for="pr in repo.review"
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

    <section v-if="failed.length" class="group">
      <h3>Selhalo</h3>
      <a
        v-for="row in failed"
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

    <section v-if="configProblems.length" class="group">
      <h3>Konfigurace</h3>
      <a
        v-for="p in configProblems"
        :key="p.kind"
        :href="p.href ?? ''"
        class="row config"
        data-test="row-config"
        :data-kind="p.kind"
      >{{ p.text }}</a>
    </section>

    <ul v-if="repo.warnings.length" class="warnings" data-test="card-warnings">
      <li v-for="(w, i) in repo.warnings" :key="i">{{ w }}</li>
    </ul>

    <footer class="activity" data-test="last-activity">
      Poslední aktivita:
      <template v-if="repo.last_activity">{{ fmtAge(since(repo.last_activity)) }} ({{ fmtTime(repo.last_activity) }})</template>
      <template v-else>žádná</template>
    </footer>
  </article>
</template>

<style scoped>
.repo-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.card-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.repo-name {
  color: var(--text);
  font-weight: 700;
  font-size: 17px;
}

.repo-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--faint);
  font-size: 13px;
}

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

.config {
  color: var(--amber);
}

.card-actions {
  display: flex;
}

.remove {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--red);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.remove:disabled {
  cursor: default;
  opacity: 0.7;
}

.state-problem {
  margin: 0;
  color: var(--red);
  font-weight: 600;
}

.warnings {
  margin: 0;
  padding-left: 18px;
  color: var(--amber);
  font-size: 13px;
}

.activity {
  color: var(--faint);
  font-size: 13px;
}
</style>

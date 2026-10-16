<script setup lang="ts">
// A repo card of the overview: the name (its path in a tooltip) with the factory buttons and the
// menu in the top right corner, what runs, waits for review, waits for auto-merge and failed, what the factory did by
// itself after a failure (auto_actions), its configuration
// problems, the factory state with the task summary and, always last, the newest activity. Every row is a link to the run, the review or the settings.
// Tasks whose PR was merged outside factory get "Otevřít sync PR" (`factory backlog sync`), or a
// link to the sync PR that is already open; the sync PR is never opened automatically.
import { computed, ref } from 'vue'
import { backlogSync, type OverviewRepo } from '@/lib/api'
import { errorText, fmtAge, fmtCost, fmtElapsed, fmtTime, ts } from '@/lib/format'
import { activeRuns, automergePrs, failedRows, problems, reviewLink, runLink } from '@/lib/overview'
import { repoHref } from '@/lib/router'
import RepoActions from './RepoActions.vue'
import RepoControls from './RepoControls.vue'
import RepoMenu from './RepoMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { NO_FEEDBACK, type ControlFeedback } from './feedback'

const props = withDefaults(defineProps<{ repo: OverviewRepo; now: number; removing?: boolean }>(), {
  removing: false,
})
const emit = defineEmits<{ remove: [repo: OverviewRepo]; changed: [] }>()

const running = computed(() => activeRuns(props.repo))
const failed = computed(() => failedRows(props.repo))
const autoActions = computed(() => props.repo.auto_actions ?? [])
const configProblems = computed(() => problems(props.repo).filter((p) => p.href !== null))
const stateProblems = computed(() => problems(props.repo).filter((p) => p.href === null))

/** Seconds from `iso` to now (the browser's clock), null for a missing timestamp. */
function since(iso: string | null | undefined): number | null {
  const t = ts(iso)
  return Number.isFinite(t) ? Math.max(0, (props.now - t) / 1000) : null
}

const feedback = ref<ControlFeedback>(NO_FEEDBACK)

const mergedOutside = computed(() => props.repo.merged_outside ?? [])
const automerge = computed(() => automergePrs(props.repo))
const syncing = ref(false)
const syncError = ref<string | null>(null)
const syncUrl = ref<string | null>(null)
const syncPrUrl = computed(() => props.repo.sync_pr?.url ?? syncUrl.value)

async function onSync() {
  syncing.value = true
  syncError.value = null
  try {
    const result = await backlogSync(props.repo.id)
    syncUrl.value = result.url
    if (!result.url) syncError.value = 'Sync PR nebyl potřeba: nic k označení jako hotové.'
  } catch (err) {
    syncError.value = errorText(err)
  } finally {
    syncing.value = false
    emit('changed')
  }
}

function reviewAge(opened: string | null, ageS: number | null): string {
  return fmtAge(since(opened) ?? ageS)
}
</script>

<template>
  <article class="repo-card" data-test="overview-card" :data-repo="repo.id">
    <header class="card-head">
      <Tooltip :text="repo.path">
        <a :href="repoHref(repo.id, 'backlog')" class="repo-name" data-test="card-name">{{ repo.name }}</a>
      </Tooltip>
      <div class="card-tools">
        <RepoActions :repo="repo" @feedback="feedback = $event" @changed="emit('changed')" />
        <RepoMenu :name="repo.name" :removing="removing" @remove="emit('remove', repo)" />
      </div>
    </header>

    <RepoControls :repo="repo" :feedback="feedback" />

    <p v-for="p in stateProblems" :key="p.kind" class="state-problem" :data-test="`state-${p.kind}`">{{ p.text }}</p>

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

    <section v-if="automerge.length" class="group" data-test="automerge">
      <h3>Čeká na automerge PR</h3>
      <a
        v-for="pr in automerge"
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

    <section v-if="mergedOutside.length" class="group" data-test="merged-outside">
      <h3>Sloučeno mimo factory</h3>
      <a
        v-for="pr in mergedOutside"
        :key="pr.task_id"
        :href="pr.url ?? undefined"
        target="_blank"
        rel="noopener"
        class="row"
        data-test="row-merged-outside"
        :data-task="pr.task_id"
      >
        <span class="task mono">{{ pr.task_id }}</span>
        <span class="title">{{ pr.task_title ?? '' }}</span>
        <span class="meta mono">{{ pr.pr_id ? `PR #${pr.pr_id}` : 'PR' }}</span>
      </a>
      <div class="sync">
        <a v-if="syncPrUrl" :href="syncPrUrl" target="_blank" rel="noopener" data-test="sync-pr-link">Sync PR čeká na merge</a>
        <button
          v-else
          type="button"
          data-test="sync-open"
          :disabled="syncing"
          :aria-busy="syncing || undefined"
          @click="onSync"
        >
          <Spinner v-if="syncing" /> Otevřít sync PR
        </button>
        <span v-if="syncError" class="sync-error" data-test="sync-error">{{ syncError }}</span>
      </div>
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

    <section v-if="autoActions.length" class="group">
      <h3>Factory zasáhla sama</h3>
      <a
        v-for="action in autoActions"
        :key="`${action.run_id}-${action.action}-${action.at}`"
        :href="runLink(repo, action.run_id)"
        class="row"
        :class="{ failed: !action.ok }"
        data-test="row-auto-action"
        :data-action="action.action"
        :data-run="action.run_id"
      >
        <span class="task mono">{{ action.task_id }}</span>
        <span class="title" data-test="row-auto-text">{{ action.text }}</span>
        <span class="meta" data-test="row-auto-age">{{ fmtAge(since(action.at)) }}</span>
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
  background: var(--panel);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.repo-name {
  color: var(--text);
  font-weight: 700;
  font-size: 17px;
}

.card-tools {
  display: flex;
  flex: none;
  align-items: center;
  gap: 6px;
  margin-left: auto;
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

.sync {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px;
}

.sync-error {
  color: var(--red);
  font-size: 14px;
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

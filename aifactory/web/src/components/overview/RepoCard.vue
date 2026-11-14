<script setup lang="ts">
import { t } from '@/lib/i18n'
import { deferredError } from '@/lib/dashboardMessages'
import { feedbackText } from '@/components/overview/feedback'
import { autoActionText, overviewWarningText } from '@/lib/dashboardMessages'
// A repo card of the overview: the name (its path in a tooltip) with the factory buttons and the
// menu in the top right corner, what runs, waits for review, waits for auto-merge and failed, what the factory did by
// itself after a failure (auto_actions), its configuration
// problems, the factory state with the task summary and, always last, the newest activity. Every row is a link to the run, the review or the settings.
// Tasks whose PR was merged outside factory get "Otevřít sync PR" (`factory backlog sync`), or a
// link to the sync PR that is already open; the sync PR is never opened automatically.
import { computed, ref } from 'vue'
import { backlogSync, type OverviewRepo } from '@/lib/api'
import { fmtAge, fmtTime, ts } from '@/lib/format'
import { problems, runLink } from '@/lib/overview'
import { repoHref } from '@/lib/router'
import RepoBacklogStatus from '@/components/overview/RepoBacklogStatus.vue'
import RepoActions from './RepoActions.vue'
import RepoControls from './RepoControls.vue'
import RepoWork from './RepoWork.vue'
import RepoMenu from './RepoMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { NO_FEEDBACK, type ControlFeedback } from './feedback'

const props = withDefaults(defineProps<{ repo: OverviewRepo; now: number; removing?: boolean; byProject?: boolean; showFinished?: boolean }>(), {
  removing: false,
  byProject: false,
  showFinished: false,
})
const emit = defineEmits<{ remove: [repo: OverviewRepo]; changed: [] }>()

const warnings = computed(() => props.repo.warning_details ?? props.repo.warnings.map(message => ({ code: 'unknown', params: {}, message })))
const autoActions = computed(() => props.repo.auto_actions ?? [])
const loading = computed(() => props.repo.state === 'timeout')
const configProblems = computed(() => problems(props.repo).filter((p) => p.href !== null))
const stateProblems = computed(() => problems(props.repo).filter((p) => p.href === null))

/** Seconds from `iso` to now (the browser's clock), null for a missing timestamp. */
function since(iso: string | null | undefined): number | null {
  const t = ts(iso)
  return Number.isFinite(t) ? Math.max(0, (props.now - t) / 1000) : null
}

const feedback = ref<ControlFeedback>(NO_FEEDBACK)

const mergedOutside = computed(() => props.repo.merged_outside ?? [])
const syncing = ref(false)
const syncError = ref<string | (() => string) | null>(null)
const syncUrl = ref<string | null>(null)
const syncPrUrl = computed(() => props.repo.sync_pr?.url ?? syncUrl.value)

async function onSync() {
  syncing.value = true
  syncError.value = null
  try {
    const result = await backlogSync(props.repo.id)
    syncUrl.value = result.url
    if (!result.url) syncError.value = () => t('dashboard.syncUnneeded')
  } catch (err) {
    syncError.value = deferredError(err)
  } finally {
    syncing.value = false
    emit('changed')
  }
}

</script>

<template>
  <article class="repo-card" :class="{ loading }" data-test="overview-card" :data-repo="repo.id" :aria-busy="loading || undefined">
    <header class="card-head">
      <Tooltip :text="repo.path">
        <a :href="repoHref(repo.id, 'backlog')" class="repo-name" data-test="card-name">{{ repo.name }}</a>
      </Tooltip>
      <div v-if="!loading" class="card-tools">
        <RepoActions :repo="repo" @feedback="feedback = $event" @changed="emit('changed')" />
        <RepoMenu :name="repo.name" :removing="removing" @remove="emit('remove', repo)" />
      </div>
    </header>

    <RepoBacklogStatus v-if="!loading" :repo="repo" />

    <div v-if="loading" class="loading-overlay" data-test="repo-loading" role="status">
      <Spinner :size="22" /> {{ t('dashboard.loadingRepo') }}
    </div>

    <template v-else>
    <p v-if="repo.stale" role="status" class="faint" data-test="repo-stale">{{ t('dashboard.staleRepo') }}</p>
    <RepoControls @changed="emit('changed')" :repo="repo" :feedback="feedback" :show-summary="!byProject || (repo.projects?.length ?? 0) === 0" />

    <p v-for="p in stateProblems" :key="p.kind" class="state-problem" :data-test="`state-${p.kind}`">{{ p.text }}</p>

    <RepoWork :repo="repo" :now="now" :by-project="byProject" :show-finished="showFinished">

      <section v-if="mergedOutside.length" class="group" data-test="merged-outside">
        <h3>{{ t('dashboard.mergedOutside') }}</h3>
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
          <a v-if="syncPrUrl" :href="syncPrUrl" target="_blank" rel="noopener" data-test="sync-pr-link">{{ t('dashboard.syncWaiting') }}</a>
          <button
            v-else
            type="button"
            data-test="sync-open"
            :disabled="syncing"
            :aria-busy="syncing || undefined"
            @click="onSync"
          >
            <Spinner v-if="syncing" /> {{ t('dashboard.openSync') }}
          </button>
          <span v-if="syncError" class="sync-error" data-test="sync-error">{{ feedbackText(syncError) }}</span>
        </div>
      </section>

    </RepoWork>

    <section v-if="autoActions.length" class="group">
      <h3>{{ t('dashboard.autoActions') }}</h3>
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
        <span class="title" data-test="row-auto-text">{{ autoActionText(action) }}</span>
        <span class="meta" data-test="row-auto-age">{{ fmtAge(since(action.at)) }}</span>
      </a>
    </section>

    <section v-if="configProblems.length" class="group">
      <h3>{{ t('dashboard.configuration') }}</h3>
      <a
        v-for="p in configProblems"
        :key="p.kind"
        :href="p.href ?? ''"
        class="row config"
        data-test="row-config"
        :data-kind="p.kind"
      >{{ p.text }}</a>
    </section>

    <ul v-if="warnings.length" class="warnings" data-test="card-warnings">
      <li v-for="(warning, i) in warnings" :key="i">
        <span data-test="warning-description">{{ overviewWarningText(warning) }}</span>
        <details><summary>{{ t('dashboard.diagnostics') }}</summary><pre>{{ warning.message }}</pre></details>
      </li>
    </ul>

    <footer class="activity" data-test="last-activity">
      {{ t('dashboard.lastActivity') }}
      <template v-if="repo.last_activity">{{ fmtAge(since(repo.last_activity)) }} ({{ fmtTime(repo.last_activity) }})</template>
      <template v-else>{{ t('dashboard.none') }}</template>
    </footer>
    </template>
  </article>
</template>

<style scoped>
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.repo-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
}

.repo-card.loading {
  min-height: 120px;
}

.loading-overlay {
  position: absolute;
  inset: 44px 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-radius: 0 0 10px 10px;
  background: var(--panel);
  color: var(--dim);
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

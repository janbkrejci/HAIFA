<script setup lang="ts">
// #/overview: what runs, waits for review and failed in every registered repo (GET /api/overview).
// Totals on top filter the cards; cards go by urgency and calm repos fold into one line each.
// Reloads every 2 s while the tab is visible, on a return to the window and by Obnovit; reads only.
// Readiness reports its progress and actionable findings above the overview.
import { computed, ref } from 'vue'
import { Plus, RefreshCw, Trash2 } from 'lucide-vue-next'
import type { RepoItem } from '@/lib/api'
import { useNow } from '@/lib/clock'
import { fmtAge, fmtTime, ts } from '@/lib/format'
import {
  TOTALS,
  activeRuns,
  matchesFilter,
  sortRepos,
  totals,
  urgency,
  useOverview,
  type OverviewFilter,
} from '@/lib/overview'
import { REPOS_ADD_HREF, repoHref } from '@/lib/router'
import { ADD_REPO_HINT, useRemoveRepo } from '@/lib/repos'
import EmptyScreen from '@/components/EmptyScreen.vue'
import RepoCard from '@/components/overview/RepoCard.vue'
import RemoveRepoDialog from '@/components/repos/RemoveRepoDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = withDefaults(defineProps<{ repos: RepoItem[] | null; error?: string | null }>(), {
  error: null,
})

const emit = defineEmits<{ changed: [] }>()

const { data, error: overviewError, loading, refresh } = useOverview()
const removal = useRemoveRepo(() => {
  void refresh()
  emit('changed')
})
const { remove, removing, error: removeError } = removal
const filter = ref<OverviewFilter | null>(null)

const sorted = computed(() => sortRepos(data.value?.repos ?? []))
const sums = computed(() => totals(data.value?.repos ?? []))
const shown = computed(() => sorted.value.filter((r) => matchesFilter(r, filter.value)))
const cards = computed(() => shown.value.filter((r) => urgency(r) !== 'calm'))
const calm = computed(() => shown.value.filter((r) => urgency(r) === 'calm'))
/** No registered repo at all (the registry list decides; the overview may lag behind it). */
const empty = computed(() => props.repos !== null && props.repos.length === 0)
const now = useNow(() => sorted.value.some((r) => activeRuns(r).length > 0))

function toggleFilter(id: OverviewFilter) {
  filter.value = filter.value === id ? null : id
}

function activity(iso: string | null): string {
  if (!iso) return 'bez aktivity'
  const t = ts(iso)
  if (!Number.isFinite(t)) return 'bez aktivity'
  return `${fmtAge((now.value - t) / 1000)} (${fmtTime(iso)})`
}
</script>

<template>
  <div v-if="empty">
    <EmptyScreen heading="Žádné repozitáře" :hint="ADD_REPO_HINT" data-test="no-repos">
      <a :href="REPOS_ADD_HREF" class="add-link" data-test="add-repo-link"><Plus :size="14" aria-hidden="true" /> Přidat repozitář</a>
    </EmptyScreen>
  </div>
  <section v-else class="overview-view" data-test="repo-page">
    <div class="head">
      <h1>Přehled</h1>
      <button
        type="button"
        class="refresh"
        data-test="overview-refresh"
        :disabled="loading"
        @click="refresh"
      >
        <RefreshCw :size="14" aria-hidden="true" :class="{ spinning: loading }" /> Obnovit
      </button>
    </div>

    <p v-if="removeError" class="error" data-test="remove-error">Repo se nepodařilo odebrat: {{ removeError }}</p>
    <p v-if="overviewError" class="error" data-test="overview-error">Přehled se nepodařilo načíst: {{ overviewError }}</p>
    <p v-if="!data && !overviewError" class="loading" data-test="overview-loading"><Spinner /> Načítám přehled…</p>

    <template v-if="data">
      <div class="totals" role="group" aria-label="Součty">
        <button
          v-for="total in TOTALS"
          :key="total.id"
          type="button"
          class="total"
          :class="[`total-${total.id}`, { active: filter === total.id }]"
          :aria-pressed="filter === total.id ? 'true' : 'false'"
          :data-test="`total-${total.id}`"
          @click="toggleFilter(total.id)"
        >
          <span class="total-count" data-test="total-count">{{ sums[total.id] }}</span>
          <span class="total-label">{{ total.label }}</span>
        </button>
      </div>

      <p v-if="filter && !shown.length" class="none" data-test="overview-none">Žádné repo neodpovídá filtru.</p>

      <div class="cards">
        <RepoCard
          v-for="repo in cards"
          :key="repo.id"
          :repo="repo"
          :now="now"
          :removing="removing === repo.id"
          @remove="remove"
        />
      </div>

      <ul v-if="calm.length" class="calm-list">
        <li v-for="repo in calm" :key="repo.id" class="calm" data-test="calm-repo" :data-repo="repo.id">
          <a :href="repoHref(repo.id, 'backlog')" class="calm-name">{{ repo.name }}</a>
          <span class="calm-state">v klidu</span>
          <span class="calm-activity" data-test="last-activity">Poslední aktivita: {{ activity(repo.last_activity) }}</span>
          <button type="button" class="calm-remove" :disabled="removing === repo.id" :aria-label="`Odebrat repozitář ${repo.name}`" data-test="calm-remove" @click="remove(repo)"><Trash2 :size="14" aria-hidden="true" /></button>
        </li>
      </ul>
    </template>
  </section>
  <RemoveRepoDialog :removal="removal" />
</template>

<style scoped>
.add-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--green);
  font-weight: 600;
}

.guide {
  max-width: 1200px;
  margin: 0 auto;
  padding: 28px 28px 0;
}

.overview-view {
  padding: 28px;
  max-width: 1200px;
  margin: 0 auto;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 0 18px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.refresh:disabled {
  cursor: default;
  opacity: 0.7;
}

.spinning {
  animation: spin 1s linear infinite;
}

.totals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.total {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.total.active {
  border-color: var(--blue);
  box-shadow: inset 0 0 0 1px var(--blue);
}

.total-count {
  font-size: 26px;
  font-weight: 700;
}

.total-label {
  color: var(--dim);
  font-size: 14px;
}

.total-running .total-count {
  color: var(--blue);
}

.total-review .total-count {
  color: var(--purple);
}

.total-failed .total-count {
  color: var(--red);
}

.total-problems .total-count {
  color: var(--amber);
}

.cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.calm-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.calm {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  white-space: nowrap;
}

.calm-name {
  color: var(--text);
  font-weight: 600;
}

.calm-state {
  color: var(--green);
  font-size: 14px;
}

.calm-activity {
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--faint);
  font-size: 13px;
}

.calm-remove {
  display: inline-flex;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--dim);
  cursor: pointer;
}

.calm-remove:hover {
  color: var(--red);
}

.loading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--dim);
}

.error {
  color: var(--red);
}

.none {
  color: var(--dim);
}
</style>

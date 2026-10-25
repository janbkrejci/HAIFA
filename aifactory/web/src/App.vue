<script setup lang="ts">
import TerminalOverlay from './components/terminal/TerminalOverlay.vue'
import { createSecretKeys } from './lib/secretKeys'
import { errorText } from './lib/format'
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { BookOpen, Sparkles, Trash2 } from 'lucide-vue-next'
import { assistant, restoreOpen, toggleOpen } from './lib/assistant'
import AssistantPanel from './components/assistant/AssistantPanel.vue'
import { fetchHealth, fetchRepos, type Health, type RepoItem } from './lib/api'
import { useCodeState } from './lib/code'
import { useBacklogStatus } from './lib/backlogStatus'
import { useConfigStatus } from './lib/configStatus'
import { openConfigCommit } from './lib/factory'
import { useLimits } from './lib/limits'
import { useRemoveRepo } from './lib/repos'
import {
  GUIDE_HREF,
  OVERVIEW_HREF,
  SCREEN_LABELS,
  usePage,
  useRepoId,
  useRoute,
} from './lib/router'
import { useTheme } from './lib/theme'
import { cancelLeave, confirmLeave, leaveDialog } from './lib/leaveGuard'
import ConfirmDialog from './components/ui/ConfirmDialog.vue'
import SetupView from './views/SetupView.vue'
import OverviewView from './views/OverviewView.vue'
import ProblemsView from './views/ProblemsView.vue'
import GuideView from './views/GuideView.vue'
import OverviewReadiness from './components/OverviewReadiness.vue'
import UpdateChip from './components/UpdateChip.vue'
import UncommittedBanner from './components/UncommittedBanner.vue'
import LibraryChip from './components/LibraryChip.vue'
import { provideReadiness } from './lib/readiness'
import ReposAddView from './views/ReposAddView.vue'
import CodeStaleBanner from './components/CodeStaleBanner.vue'
import EmptyScreen from './components/EmptyScreen.vue'
import LimitsBar from './components/LimitsBar.vue'
import MachineHarnessesDialog from './components/MachineHarnessesDialog.vue'
import RepoScreen from './components/RepoScreen.vue'
import RepoSwitcher from './components/RepoSwitcher.vue'
import RemoveRepoDialog from './components/repos/RemoveRepoDialog.vue'
import Spinner from './components/ui/Spinner.vue'
import Tooltip from './components/ui/Tooltip.vue'

const terminalOpen = ref(false)
const secretKeys = createSecretKeys()
function terminalKeydown(event: KeyboardEvent) {
  if (secretKeys(event)) terminalOpen.value = !terminalOpen.value
}

const route = useRoute()
const readiness = provideReadiness()
const page = usePage()
const viewPage = page
const repoId = useRepoId()
const { theme, toggle } = useTheme()
const themeLabel = computed(() =>
  theme.value === 'dark' ? 'Přepnout na světlý motiv' : 'Přepnout na tmavý motiv',
)

const health = ref<Health | null>(null)
const healthError = ref(false)

// The registered repositories: the switcher, the overview and whether the URL's repo exists.
const repos = ref<RepoItem[] | null>(null)
const reposError = ref<string | null>(null)
let reposGeneration = 0

async function loadRepos(): Promise<void> {
  const mine = ++reposGeneration
  try {
    const list = await fetchRepos()
    if (mine !== reposGeneration) return
    repos.value = list.repos ?? []
    reposError.value = null
  } catch (err) {
    if (mine !== reposGeneration) return
    reposError.value = errorText(err)
  }
}

const reloadRepos = () => void loadRepos()
watch([page, repoId], reloadRepos)

/** A repo just added on #/repos/add: the switcher and the overview know it; the page shows what next. */
async function onAdded(): Promise<void> {
  await loadRepos()
}

/** The open repo whose folder is gone can leave the dashboard (back to the overview). */
const missingRemoval = useRemoveRepo(() => {
  window.location.hash = OVERVIEW_HREF
  reloadRepos()
})

const repoIds = computed(() => (repos.value ?? []).map((r) => r.id))
const currentRepo = computed(() => repos.value?.find((r) => r.id === repoId.value) ?? null)
/** The repo page waits for the list once; a failed list still shows the repo (the API decides). */
const repoState = computed<'loading' | 'unknown' | 'ok'>(() => {
  if (repos.value === null) return reposError.value === null ? 'loading' : 'ok'
  return currentRepo.value ? 'ok' : 'unknown'
})

watchEffect(() => {
  if (page.value === 'repo') {
    const name = currentRepo.value?.name ?? repoId.value ?? ''
    document.title = `${name} · ${SCREEN_LABELS[route.value]} · HAIFA`
  } else if (page.value === 'setup') {
    document.title = 'Knihovna · HAIFA'
  } else if (page.value === 'repos-add') {
    document.title = 'Přidat repozitář · HAIFA'
  } else if (page.value === 'problems') {
    document.title = 'Problémy a řešení · HAIFA'
  } else if (page.value === 'guide') {
    document.title = 'Příručka · HAIFA'
  } else {
    document.title = 'Přehled · HAIFA'
  }
})

const code = useCodeState()
/** On a known repo page the limits of its harnesses; elsewhere (and for an unknown id) the machine's. */
const limitsRepo = computed(() => (page.value === 'repo' && repoState.value === 'ok' ? repoId.value : null))
const limits = useLimits(limitsRepo)
const harnessDialog = ref(false)
function openHarnesses() { harnessDialog.value = true }
const backlogStatus = useBacklogStatus()
/** The red chip of the uncommitted backlog sits in the topbar of a repo page (RepoScreen refreshes it). */
const showBacklogChip = computed(() => page.value === 'repo' && repoState.value === 'ok')
const commitBacklog = () => void backlogStatus.commit()
/** The red chip of the uncommitted config opens its reviewed commit on the Factory screen. */
const configStatus = useConfigStatus()
const commitConfig = () => openConfigCommit(repoId.value ?? '')

onMounted(async () => {
  window.addEventListener('keydown', terminalKeydown, true)
  window.addEventListener('harness-settings-open', openHarnesses)
  window.addEventListener('focus', reloadRepos)
  window.addEventListener('factory-applied', reloadRepos)
  void loadRepos()
  restoreOpen()
  try {
    health.value = await fetchHealth()
  } catch {
    healthError.value = true
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', terminalKeydown, true)
  window.removeEventListener('harness-settings-open', openHarnesses)
  window.removeEventListener('focus', reloadRepos)
  window.removeEventListener('factory-applied', reloadRepos)
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="topbar-left">
        <svg class="logo" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="4" y="6" width="17" height="5" rx="2.5" fill="#e8b64a" />
          <rect x="8" y="13.5" width="20" height="5" rx="2.5" fill="#c89bff" />
          <rect x="4" y="21" width="13" height="5" rx="2.5" fill="#5ad2dd" />
        </svg>
        <a class="brand" :href="OVERVIEW_HREF">HAIFA</a>
      </div>

      <div class="topbar-right">
        <UncommittedBanner
          v-if="showBacklogChip"
          kind="backlog"
          title="Backlog"
          commit-label="Commitnout backlog"
          chip
          :status="backlogStatus.status.value"
          :committing="backlogStatus.committing.value"
          :commit-error="backlogStatus.commitError.value"
          :pr="backlogStatus.pendingPr.value"
          @commit="commitBacklog"
        />
        <UncommittedBanner
          v-if="showBacklogChip"
          kind="config"
          title="Konfigurace"
          chip-text="Necommitnutá konfigurace"
          commit-label="Commitnout konfiguraci"
          chip
          :panel="false"
          :status="configStatus.status.value"
          @commit="commitConfig"
        />
        <UpdateChip />
        <OverviewReadiness chip />
        <LibraryChip />
        <LimitsBar :providers="limits.providers.value" :loading="limits.loading.value" :usable="limits.usable.value" @open="harnessDialog = true" />
        <Tooltip text="AI průvodce: zeptej se na repa, tasky a běhy">
          <button
            class="guide-link"
            :class="{ active: assistant.open }"
            type="button"
            aria-label="AI průvodce"
            :aria-pressed="assistant.open"
            data-test="assistant-toggle"
            @click="toggleOpen"
          >
            <Sparkles class="theme-icon" aria-hidden="true" />
          </button>
        </Tooltip>
        <Tooltip text="Uživatelská a administrační příručka">
          <a class="guide-link" :class="{ active: viewPage === 'guide' }" :href="GUIDE_HREF" aria-label="Příručka" data-test="guide-link">
            <BookOpen class="theme-icon" aria-hidden="true" />
          </a>
        </Tooltip>
        <Tooltip :text="themeLabel">
        <button class="theme-toggle" type="button" :aria-label="themeLabel" @click="toggle">
          <svg v-if="theme === 'dark'" class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
          <svg v-else class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        </button>
        </Tooltip>
        <RepoSwitcher :repos="repos" :health="health" :health-error="healthError" @refresh="reloadRepos" />
      </div>
    </header>
    <CodeStaleBanner
      :stale="code.stale.value"
      :restarting="code.restarting.value"
      :error="code.error.value"
      @restart="code.restart"
    />
    <template v-if="viewPage === 'repo'">
      <main v-if="repoState === 'loading'" class="page-loading" data-test="repo-loading">
        <Spinner /> Načítám repozitáře…
      </main>
      <main v-else-if="repoState === 'unknown'">
        <EmptyScreen
          :heading="`Repo ${repoId} v dashboardu není`"
          hint="Dashboard takový repozitář nezná. Vyber jiný v přehledu."
          data-test="unknown-repo"
        >
          <a :href="OVERVIEW_HREF" class="overview-link" data-test="unknown-repo-overview">Přehled repozitářů</a>
        </EmptyScreen>
      </main>
      <main v-else-if="currentRepo?.status === 'missing'">
        <EmptyScreen
          :heading="`Složka repozitáře ${currentRepo.name} chybí`"
          :hint="`${currentRepo.path} neexistuje. Repo můžeš odebrat z dashboardu.`"
          data-test="missing-repo"
        >
          <button
            type="button"
            class="remove-button"
            :disabled="missingRemoval.removing.value !== null"
            data-test="missing-remove"
            @click="missingRemoval.remove(currentRepo)"
          >
            <Trash2 :size="14" aria-hidden="true" /> Odebrat z dashboardu
          </button>
          <p v-if="missingRemoval.error.value" class="remove-error" data-test="remove-error">
            Repo se nepodařilo odebrat: {{ missingRemoval.error.value }}
          </p>
        </EmptyScreen>
        <RemoveRepoDialog :removal="missingRemoval" />
      </main>
      <RepoScreen v-else :key="repoId ?? ''" :demo="currentRepo?.demo === true" :path="currentRepo?.path ?? null" />
    </template>
    <main v-else-if="viewPage === 'repos-add'">
      <ReposAddView @added="onAdded" />
    </main>
    <main v-else-if="viewPage === 'setup'">
      <SetupView />
    </main>
    <main v-else-if="viewPage === 'guide'">
      <GuideView />
    </main>
    <main v-else-if="viewPage === 'problems'">
      <ProblemsView @changed="reloadRepos" />
    </main>
    <main v-else>
      <OverviewView :repos="repos" :error="reposError" @changed="reloadRepos" />
    </main>
  </div>
  <MachineHarnessesDialog :open="harnessDialog" @close="harnessDialog = false" @saved="limits.refresh(); readiness.refresh(true)" @tested="limits.refresh(); readiness.refresh(true)" />
  <AssistantPanel :repos="repoIds" />
  <TerminalOverlay v-if="terminalOpen" @close="terminalOpen = false" />
  <ConfirmDialog v-bind="leaveDialog" @confirm="confirmLeave" @cancel="cancelLeave" />
</template>

<style scoped>
.page-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 28px;
  color: var(--dim);
}

.overview-link {
  color: var(--blue);
}

.remove-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--red);
  font: inherit;
  cursor: pointer;
}

.remove-button:disabled {
  cursor: default;
  opacity: 0.7;
}

.remove-error {
  margin: 10px 0 0;
  color: var(--red);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 28px;
  background: rgba(11, 15, 24, 0.72);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  position: sticky;
  top: 0;
  z-index: 10;
}

[data-theme="light"] .topbar {
  background: rgba(255, 255, 255, 0.85);
}

.topbar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    rgba(200, 155, 255, 0.45),
    rgba(90, 210, 221, 0.35) 40%,
    rgba(90, 210, 221, 0.06)
  );
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
  justify-content: flex-end;
  min-width: 0;
}

.logo {
  width: 28px;
  height: 28px;
  flex: none;
  filter: drop-shadow(0 0 8px rgba(200, 155, 255, 0.35));
}

.brand {
  text-decoration: none;
  background: linear-gradient(90deg, var(--purple), var(--cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: 700;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.theme-toggle,
.guide-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

[data-theme="light"] .theme-toggle,
[data-theme="light"] .guide-link {
  background: rgba(255, 255, 255, 0.7);
}

.theme-toggle:hover,
.guide-link:hover {
  background: var(--panel-3);
  border-color: var(--border);
}

[data-theme="light"] .theme-toggle:hover,
[data-theme="light"] .guide-link:hover {
  background: rgba(255, 255, 255, 0.9);
}

.guide-link.active {
  color: var(--purple);
  border-color: var(--purple);
}

.theme-icon {
  width: 18px;
  height: 18px;
}

</style>

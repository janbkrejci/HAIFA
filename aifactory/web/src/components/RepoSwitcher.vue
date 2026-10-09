<script setup lang="ts">
// The repo switcher of the topbar: the current repo (or page) and the dashboard version; its menu
// leads to the overview, every registered repo (same screen, no parameters) and the repo pages.
// On opening it reads GET /api/overview for the running, review and failed counts of each repo.
import { computed, onBeforeUnmount, ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { fetchOverview, type Health, type RepoItem } from '@/lib/api'
import { countsById, type RepoCounts } from '@/lib/overview'
import { REPO_STATUS_TEXT } from '@/lib/repos'
import { OVERVIEW_HREF, REPOS_ADD_HREF, repoHref, usePage, useRepoId, useRoute } from '@/lib/router'

const props = defineProps<{
  repos: RepoItem[] | null
  health: Health | null
  healthError: boolean
}>()

const emit = defineEmits<{ refresh: [] }>()

const page = usePage()
const repoId = useRepoId()
const screen = useRoute()

const root = ref<HTMLElement | null>(null)
const open = ref(false)

/** Counts per repo id from the overview, read on every opening. */
const counts = ref<Record<string, RepoCounts>>({})
let countsGeneration = 0

async function loadCounts() {
  const mine = ++countsGeneration
  try {
    const data = await fetchOverview()
    if (mine === countsGeneration) counts.value = countsById(data)
  } catch {
    // the menu works without counts
  }
}

const COUNTS: readonly { key: keyof RepoCounts; label: string }[] = [
  { key: 'running', label: 'běží' },
  { key: 'review', label: 'čeká na review' },
  { key: 'failed', label: 'selhalo' },
]

/** The status label of a repo in the menu; a healthy repo has none. */
function statusLabel(repo: RepoItem): string | null {
  return repo.status === 'ok' ? null : (REPO_STATUS_TEXT[repo.status] ?? repo.status)
}

const current = computed(() => {
  if (page.value === 'repo') {
    const id = repoId.value ?? ''
    return props.repos?.find((r) => r.id === id)?.name ?? id
  }
  if (page.value === 'setup') return 'Tento počítač'
  if (page.value === 'library') return 'Knihovna'
  if (page.value === 'problems') return 'Problémy a řešení'
  return page.value === 'repos-add' ? 'Přidat repozitář' : 'Přehled'
})

/** The folder that holds the repo (the path without its last segment). */
function parentFolder(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, '')
  const cut = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'))
  if (cut < 0) return ''
  return cut === 0 ? trimmed.slice(0, 1) : trimmed.slice(0, cut)
}

function onOutside(event: Event) {
  const target = event.target as Node | null
  if (target && root.value?.contains(target)) return
  close()
}

function onKeydown(event: Event) {
  if ((event as KeyboardEvent).key === 'Escape') close()
}

function listen(on: boolean) {
  const method = on ? 'addEventListener' : 'removeEventListener'
  document[method]('mousedown', onOutside, true)
  document[method]('keydown', onKeydown)
}

function close() {
  if (!open.value) return
  open.value = false
  listen(false)
}

function toggle() {
  if (open.value) {
    close()
    return
  }
  open.value = true
  listen(true)
  emit('refresh')
  void loadCounts()
}

onBeforeUnmount(() => listen(false))
</script>

<template>
  <div ref="root" class="repo-switcher" data-test="repo-switcher">
    <button
      type="button"
      class="switcher-button"
      aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'"
      data-test="switcher-button"
      @click="toggle"
    >
      <span v-if="!healthError" class="live-dot" />
      <span class="current" data-test="switcher-current">{{ current }}</span>
      <span v-if="healthError" class="api-down">API nedostupné</span>
      <span v-else-if="health" class="version">v{{ health.version }}</span>
      <ChevronDown class="chevron" :size="14" aria-hidden="true" />
    </button>
    <div v-if="open" class="switcher-menu" role="menu" data-test="switcher-menu">
      <a
        :href="OVERVIEW_HREF"
        role="menuitem"
        class="item"
        :class="{ active: page === 'overview' }"
        data-test="switch-overview"
        @click="close"
      >Přehled</a>
      <a href="#/setup" role="menuitem" class="item" :class="{ active: page === 'setup' }" data-test="switch-setup" @click="close">Tento počítač</a>
      <a href="#/library" role="menuitem" class="item" :class="{ active: page === 'library' }" data-test="switch-library" @click="close">Knihovna</a>
      <div v-if="repos && repos.length" class="separator" />
      <a
        v-for="repo in repos ?? []"
        :key="repo.id"
        :href="repoHref(repo.id, screen)"
        role="menuitem"
        class="item repo-item"
        :class="{ active: page === 'repo' && repo.id === repoId }"
        :data-test="`switch-repo-${repo.id}`"
        @click="close"
      >
        <span class="repo-name">{{ repo.name }}</span>
        <span class="repo-parent" data-test="repo-parent">{{ parentFolder(repo.path) }}</span>
        <span v-if="statusLabel(repo)" class="repo-label" data-test="repo-label">{{ statusLabel(repo) }}</span>
        <span v-if="counts[repo.id]" class="repo-counts" data-test="repo-counts">
          <template v-for="c in COUNTS" :key="c.key">
            <span
              v-if="counts[repo.id][c.key] > 0"
              class="count"
              :class="`count-${c.key}`"
              :aria-label="`${counts[repo.id][c.key]} ${c.label}`"
              :data-test="`count-${c.key}`"
            >{{ counts[repo.id][c.key] }}</span>
          </template>
        </span>
      </a>
      <div class="separator" />
      <a :href="REPOS_ADD_HREF" role="menuitem" class="item" data-test="switch-add" @click="close">Přidat repozitář…</a>
    </div>
  </div>
</template>

<style scoped>
.repo-switcher {
  position: relative;
  flex: none;
}

.switcher-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 280px;
  padding: 2px 6px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--dim);
  font: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
}

.switcher-button:hover,
.switcher-button[aria-expanded='true'] {
  border-color: var(--border);
  background: var(--panel-2);
  color: var(--text);
}

.current {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.version {
  color: var(--faint);
  font-size: 14px;
}

.chevron {
  flex: none;
  color: var(--faint);
}

.live-dot {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 10px rgba(74, 222, 128, 0.7);
  animation: pulse 1.6s ease-in-out infinite;
}

.api-down {
  color: var(--red);
}

.switcher-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: var(--z-dropdown);
  display: flex;
  flex-direction: column;
  min-width: 240px;
  max-width: 420px;
  max-height: 70vh;
  overflow-y: auto;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 15px;
  box-shadow: var(--shadow-pop);
}

.item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  color: var(--text);
  white-space: nowrap;
}

.item:hover {
  background: rgba(108, 182, 255, 0.14);
}

.item.active {
  color: var(--blue);
  font-weight: 600;
}

.repo-parent {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--faint);
  font-size: 13px;
}

.repo-label {
  margin-left: auto;
  color: var(--amber);
  font-size: 13px;
}

.repo-counts {
  display: inline-flex;
  gap: 4px;
  margin-left: auto;
}

.repo-label + .repo-counts {
  margin-left: 0;
}

.count {
  min-width: 18px;
  padding: 0 6px;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  line-height: 18px;
}

.count-running {
  background: rgba(108, 182, 255, 0.18);
  color: var(--blue);
}

.count-review {
  background: rgba(200, 155, 255, 0.18);
  color: var(--purple);
}

.count-failed {
  background: rgba(255, 107, 107, 0.18);
  color: var(--red);
}

.separator {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
</style>

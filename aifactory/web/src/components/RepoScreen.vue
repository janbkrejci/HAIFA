<script setup lang="ts">
// Everything of one repo page: the config and backlog banners, the live updates and the screen.
// App.vue keys it by the repo id, so a switch of the repo drops all of it (view data, run
// cursors, subscriptions, banners) and the new repo starts clean.
import { computed, onBeforeUnmount, onMounted, watch, type Component } from 'vue'
import { Activity, Factory, GitPullRequest, ListTodo, Settings } from 'lucide-vue-next'
import { useConfigStatus } from '@/lib/configStatus'
import { resetBacklogStatus, useBacklogStatus } from '@/lib/backlogStatus'
import { useLive } from '@/lib/live'
import { refreshNames, resetNames } from '@/lib/names'
import { SCREENS, currentRepoId, here, repoHref, useRoute, type Screen } from '@/lib/router'
import BacklogView from '@/views/BacklogView.vue'
import RunsView from '@/views/RunsView.vue'
import ReviewView from '@/views/ReviewView.vue'
import SettingsView from '@/views/SettingsView.vue'
import FactoryView from '@/views/FactoryView.vue'
import UncommittedBanner from './UncommittedBanner.vue'

const VIEWS: Record<Screen, Component> = {
  backlog: BacklogView,
  runs: RunsView,
  review: ReviewView,
  factory: FactoryView,
  settings: SettingsView,
}

const ICONS: Record<Screen, Component> = {
  backlog: ListTodo,
  runs: Activity,
  review: GitPullRequest,
  factory: Factory,
  settings: Settings,
}

// the previous repo's backlog status and names never show here
resetBacklogStatus()
resetNames()

const route = useRoute()
const view = computed(() => VIEWS[route.value])

function commitConfig() {
  const href = repoHref(currentRepoId() ?? '', 'factory', 'config_commit')
  if (window.location.hash === href) window.dispatchEvent(new Event('factory-commit-preview'))
  else window.location.hash = href
}
const configStatus = useConfigStatus(currentRepoId() ?? '')
const refreshConfig = () => void configStatus.refresh()
watch(route, refreshConfig)
const backlogStatus = useBacklogStatus()
const refreshBacklog = () => void backlogStatus.refresh()
const commitBacklog = () => void backlogStatus.commit()
const refreshStatuses = () => {
  refreshConfig()
  refreshBacklog()
}
// The names of projects, steps and tasks in the tooltips of codes follow the backlog live.
const reloadNames = () => void refreshNames()
useLive({
  files: (event) => {
    if (event.areas.includes('factory')) refreshConfig()
    if (event.areas.includes('backlog')) refreshBacklog()
    if (event.areas.includes('backlog') || event.areas.includes('factory')) reloadNames()
  },
  resync: () => {
    refreshStatuses()
    reloadNames()
  },
})

onMounted(() => {
  refreshStatuses()
  reloadNames()
  window.addEventListener('focus', refreshStatuses)
  window.addEventListener('factory-applied', refreshStatuses)
})

onBeforeUnmount(() => {
  window.removeEventListener('focus', refreshStatuses)
  window.removeEventListener('factory-applied', refreshStatuses)
  resetBacklogStatus()
  resetNames()
})
</script>

<template>
  <UncommittedBanner
    kind="config"
    title="Konfigurace v .factory/"
    commit-label="Commitnout konfiguraci"
    :status="configStatus.status.value"
    :status-error="configStatus.error.value"
    @commit="commitConfig"
  >
    <template #title>Konfigurace v <code>.factory/</code></template>
  </UncommittedBanner>
  <UncommittedBanner
    kind="backlog"
    title="Backlog"
    commit-label="Commitnout backlog"
    floating
    :status="backlogStatus.status.value"
    :committing="backlogStatus.committing.value"
    :commit-error="backlogStatus.commitError.value"
    @commit="commitBacklog"
  />
  <main>
    <nav class="screen-tabs" aria-label="Obrazovky repozitáře">
      <a
        v-for="screen in SCREENS"
        :key="screen.id"
        :href="here(screen.id)"
        :class="{ active: route === screen.id }"
        :aria-current="route === screen.id ? 'page' : undefined"
        :data-screen="screen.id"
      >
        <component :is="ICONS[screen.id]" :size="16" aria-hidden="true" />
        <span>{{ screen.label }}</span>
      </a>
    </nav>
    <component :is="view" />
  </main>
</template>

<style scoped>
.screen-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 28px 0;
  border-bottom: 1px solid var(--border-soft);
  overflow-x: auto;
}

.screen-tabs a {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 7px;
  margin-bottom: -1px;
  padding: 8px 14px;
  border-bottom: 2px solid transparent;
  color: var(--dim);
  font-size: 15px;
  white-space: nowrap;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.screen-tabs a:hover {
  color: var(--text);
}

.screen-tabs a.active {
  border-bottom-color: var(--cyan);
  color: var(--text);
  font-weight: 600;
}
</style>

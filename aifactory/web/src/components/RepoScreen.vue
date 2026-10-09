<script setup lang="ts">
// Everything of one repo page: the config and backlog banners, the live updates and the screen.
// App.vue keys it by the repo id, so a switch of the repo drops all of it (view data, run
// cursors, subscriptions, banners) and the new repo starts clean.
import { computed, onBeforeUnmount, onMounted, watch, type Component } from 'vue'
import { useConfigStatus } from '@/lib/configStatus'
import { resetBacklogStatus, useBacklogStatus } from '@/lib/backlogStatus'
import { useLive } from '@/lib/live'
import { refreshNames, resetNames } from '@/lib/names'
import { currentRepoId, repoHref, useRoute, type Screen } from '@/lib/router'
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
    <component :is="view" />
  </main>
</template>

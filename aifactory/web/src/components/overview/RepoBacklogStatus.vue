<script setup lang="ts">
import { computed } from 'vue'
import type { OverviewRepo } from '@/lib/api'
import { backlogText } from '@/lib/overview'
import { repoHref } from '@/lib/router'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ repo: OverviewRepo }>()
const text = computed(() => backlogText(props.repo))
</script>

<template>
  <Tooltip v-if="text" :text="repo.backlog?.error ?? ''">
    <a :href="repoHref(repo.id, 'backlog')" class="backlog-status" data-test="repo-backlog-status" :data-state="repo.backlog?.state ?? 'error'">{{ text }}</a>
  </Tooltip>
</template>

<style scoped>
.backlog-status { color: var(--amber); font-size: 14px; }
</style>

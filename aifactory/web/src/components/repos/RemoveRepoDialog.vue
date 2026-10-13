<script setup lang="ts">
// The confirmation of removing a repository from the dashboard (useRemoveRepo).
import type { RepoRemover } from '@/lib/repos'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

defineProps<{ removal: RepoRemover }>()
</script>

<template>
  <ConfirmDialog v-bind="removal.dialog" @confirm="removal.confirm" @cancel="removal.cancel" />
</template>

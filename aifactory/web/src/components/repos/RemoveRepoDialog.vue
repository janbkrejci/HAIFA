<script setup lang="ts">
// The confirmation of removing a repository (useRemoveRepo): what the commit deletes and what
// blocks the removal.
import { computed } from 'vue'
import type { RepoRemover } from '@/lib/repos'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const props = defineProps<{ removal: RepoRemover }>()

const plan = computed(() => props.removal.plan.value)
</script>

<template>
  <ConfirmDialog v-bind="removal.dialog" @confirm="removal.confirm" @cancel="removal.cancel">
    <template v-if="plan">
      <p class="files" data-test="removal-files">
        {{ plan.files.length ? `Commit změní ${plan.files.length} ${plan.files.length === 1 ? 'soubor' : (plan.files.length < 5 ? 'soubory' : 'souborů')}.` : 'V repu není nic z factory ke smazání.' }}
      </p>
      <ul v-if="plan.blockers.length" class="blockers" role="alert" data-test="removal-blockers">
        <li v-for="blocker in plan.blockers" :key="blocker.code" data-test="removal-blocker">
          {{ blocker.fix ? `${blocker.message} ${blocker.fix}` : blocker.message }}
        </li>
      </ul>
    </template>
  </ConfirmDialog>
</template>

<style scoped>
.files {
  margin: 0 0 12px;
  color: var(--dim);
}

.blockers {
  margin: 0;
  padding-left: 18px;
  color: var(--red);
}
</style>

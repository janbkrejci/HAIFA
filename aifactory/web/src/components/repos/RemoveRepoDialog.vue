<script setup lang="ts">
// The confirmation of removing a repository (useRemoveRepo): what the commit deletes, the
// repo's own items that can move to the library first, and what blocks the removal.
import { computed } from 'vue'
import { stateText } from '@/lib/library'
import type { RepoRemover } from '@/lib/repos'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const props = defineProps<{ removal: RepoRemover }>()

const plan = computed(() => props.removal.plan.value)
const choices = computed(() => props.removal.choices.value)
</script>

<template>
  <ConfirmDialog v-bind="removal.dialog" @confirm="removal.confirm" @cancel="removal.cancel">
    <template v-if="plan">
      <p class="files" data-test="removal-files">
        {{ plan.files.length ? `Commit změní ${plan.files.length} ${plan.files.length === 1 ? 'soubor' : (plan.files.length < 5 ? 'soubory' : 'souborů')}.` : 'V repu není nic z factory ke smazání.' }}
      </p>
      <fieldset v-if="choices.length" class="own" data-test="removal-own-items">
        <legend>Vlastní položky repa</legend>
        <label v-for="choice in choices" :key="`${choice.item.type}/${choice.item.name}`" class="own-item" data-test="removal-own-item">
          <input v-model="choice.export" type="checkbox" data-test="removal-export" />
          <span>Přesunout do knihovny: {{ choice.item.type }} <strong>{{ choice.item.name }}</strong> <span class="dim">({{ stateText(choice.item.state) }})</span></span>
        </label>
      </fieldset>
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

.own {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.own legend {
  padding: 0 4px;
  color: var(--dim);
}

.own-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  cursor: pointer;
}

.dim {
  color: var(--dim);
}

.blockers {
  margin: 0;
  padding-left: 18px;
  color: var(--red);
}
</style>

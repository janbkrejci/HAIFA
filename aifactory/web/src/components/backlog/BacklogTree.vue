<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from 'lucide-vue-next'
import { DEFAULT_LEVELS, levelNoun, type BacklogNode } from '@/lib/backlog'
import { newContainerHref } from '@/lib/router'
import TreeNode from './TreeNode.vue'

const props = defineProps<{
  items: BacklogNode[]
  levels: string[]
  /** A filter hides every item of a non-empty backlog. */
  filtered?: boolean
}>()
/** A switch of a project or step was written: the tree should be loaded again. */
const emit = defineEmits<{ changed: []; 'clear-filter': [] }>()

const topNoun = computed(() => levelNoun(props.levels[0] ?? DEFAULT_LEVELS[0] ?? 'project'))
</script>

<template>
  <div v-if="!items.length && filtered" class="empty-state" data-test="empty-filter">
    <p>Filtru nic neodpovídá.</p>
    <button type="button" class="button" data-test="clear-filter" @click="emit('clear-filter')">Zrušit filtr</button>
  </div>
  <div v-else-if="!items.length" class="empty-state" data-test="empty-tree">
    <p>Backlog je prázdný. Založ první {{ topNoun }}.</p>
    <a :href="newContainerHref()" class="button" data-test="empty-new-project">
      <Plus :size="16" /> Nový {{ topNoun }}
    </a>
  </div>
  <ul v-else class="tree" data-test="tree">
    <TreeNode
      v-for="node in items"
      :key="node.kind === 'task' ? node.path : (node.id ?? node.path)"
      :node="node"
      :levels="levels"
      :depth="0"
      @changed="emit('changed')"
    />
  </ul>
</template>

<style scoped>
.tree {
  list-style: none;
  margin: 0;
  padding: 0;
}

.empty-state {
  display: flex;
  align-items: center;
  gap: 12px;
}

.empty-state p {
  margin: 0;
}

.button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}
</style>

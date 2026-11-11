<script setup lang="ts">
import { computed } from 'vue'
import {
  levelLabel,
  type BacklogFilters,
  type BacklogMode,
  type ScopeOption,
} from '@/lib/backlog'
import type { SelectOption } from '@/lib/select'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const props = withDefaults(
  defineProps<{
    filters: BacklogFilters
    mode: BacklogMode
    /** `levels` of the backlog: label of the project filter. */
    levels?: string[]
    /** Projects of the shared backlog filter. */
    projects?: ScopeOption[]
    /** The „Skrýt hotové“ switch. */
    hideDone?: boolean
  }>(),
  { levels: () => [], projects: () => [], hideDone: false },
)

const emit = defineEmits<{
  'update:filters': [filters: BacklogFilters]
  'update:mode': [mode: BacklogMode]
  'update:hideDone': [on: boolean]
}>()

const projectLabel = computed(() => levelLabel(props.levels[0] ?? 'project'))

function scopeLabel(o: ScopeOption): string {
  return o.title ? `${o.id} – ${o.title}` : o.id
}

const projectChoices = computed<SelectOption[]>(() => [
  { value: '', label: 'vše' },
  ...props.projects.map((p) => ({ value: p.id, label: scopeLabel(p) })),
])

function setProject(value: string) {
  emit('update:filters', { project: value || undefined })
}
</script>

<template>
  <div class="filters">
    <label>
      {{ projectLabel }}
      <SelectMenu
        data-test="project-filter"
        :label="projectLabel"
        :model-value="filters.project ?? ''"
        :options="projectChoices"
        @update:model-value="setProject"
      />
    </label>
    <label class="check">
      <input
        type="checkbox"
        data-test="hide-done"
        :checked="hideDone"
        @change="emit('update:hideDone', ($event.target as HTMLInputElement).checked)"
      />
      Skrýt hotové
    </label>
    <div class="modes" role="group" aria-label="Zobrazení">
      <button
        type="button"
        data-test="mode-tree"
        :class="{ active: mode === 'tree' }"
        @click="emit('update:mode', 'tree')"
      >
        Strom
      </button>
      <button
        type="button"
        data-test="mode-kanban"
        :class="{ active: mode === 'kanban' }"
        @click="emit('update:mode', 'kanban')"
      >
        Kanban
      </button>
    </div>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 14px;
  color: var(--dim);
}

label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.check {
  gap: 6px;
  cursor: pointer;
}

.modes {
  display: inline-flex;
  margin-left: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.modes button {
  padding: 5px 14px;
  border: 0;
  background: var(--panel-2);
  color: var(--dim);
  font: inherit;
  cursor: pointer;
}

.modes button.active {
  background: var(--panel-3);
  color: var(--text);
  font-weight: 600;
}
</style>

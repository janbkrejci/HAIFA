<script setup lang="ts">
import { computed } from 'vue'
import {
  levelLabel,
  stepOptions,
  type BacklogFilters,
  type BacklogMode,
  type ScopeOption,
  type StepRef,
} from '@/lib/backlog'
import type { SelectOption } from '@/lib/select'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const props = withDefaults(
  defineProps<{
    filters: BacklogFilters
    mode: BacklogMode
    /** `levels` of the backlog: labels of the project and step filters. */
    levels?: string[]
    /** Projects of the kanban filter. */
    projects?: ScopeOption[]
    /** Every step (with its project) of the kanban filter. */
    steps?: StepRef[]
    /** The „Skrýt hotové“ switch. */
    hideDone?: boolean
  }>(),
  { levels: () => [], projects: () => [], steps: () => [], hideDone: false },
)

const emit = defineEmits<{
  'update:filters': [filters: BacklogFilters]
  'update:mode': [mode: BacklogMode]
  'update:hideDone': [on: boolean]
}>()

const kanban = computed(() => props.mode === 'kanban')
const projectLabel = computed(() => levelLabel(props.levels[0] ?? 'project'))
const stepLabel = computed(() => levelLabel(props.levels[props.levels.length - 2] ?? 'step'))
/** Fewer than three levels: no step between project and task. */
const hasSteps = computed(() => props.levels.length >= 3)

function scopeLabel(o: ScopeOption): string {
  return o.title ? `${o.id} – ${o.title}` : o.id
}

const projectChoices = computed<SelectOption[]>(() => [
  { value: '', label: 'vše' },
  ...props.projects.map((p) => ({ value: p.id, label: scopeLabel(p) })),
])

const stepChoices = computed<SelectOption[]>(() => [
  { value: '', label: 'vše' },
  ...stepOptions(props.steps, props.filters.project).map((s) => ({ value: s.id, label: scopeLabel(s) })),
])

function setProject(value: string) {
  const project = value || undefined
  const step = props.filters.step
  const keep = step && (!project || props.steps.some((s) => s.id === step && s.project === project))
  emit('update:filters', { ...props.filters, project, step: keep ? step : undefined })
}

function setStep(value: string) {
  emit('update:filters', { ...props.filters, step: value || undefined })
}
</script>

<template>
  <div class="filters">
    <template v-if="kanban">
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
      <label v-if="hasSteps">
        {{ stepLabel }}
        <SelectMenu
          data-test="step-filter"
          :label="stepLabel"
          :model-value="filters.step ?? ''"
          :options="stepChoices"
          @update:model-value="setStep"
        />
      </label>
    </template>
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

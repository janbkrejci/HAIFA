<script setup lang="ts">
// Picks backlog codes (the links "Závisí na" and "Související" of a task) from a list instead of
// typing them: the chosen codes are chips with a remove button, a dropdown adds another one.
// A chosen code missing from the list (e.g. an unknown reference already in the file) stays a chip.
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import type { SelectOption } from '@/lib/select'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  modelValue: string[]
  /** Every code that can be chosen; the chosen ones are left out of the dropdown. */
  options: SelectOption[]
  label: string
  disabled?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const free = computed<SelectOption[]>(() =>
  props.options.filter((o) => !props.modelValue.includes(o.value)),
)
const titles = computed(() => new Map(props.options.map((o) => [o.value, o.label])))

function add(id: string) {
  if (id && !props.modelValue.includes(id)) emit('update:modelValue', [...props.modelValue, id])
}

function remove(id: string) {
  emit('update:modelValue', props.modelValue.filter((v) => v !== id))
}
</script>

<template>
  <div class="id-picker">
    <ul v-if="modelValue.length" class="picked">
      <li v-for="id in modelValue" :key="id" :data-picked="id">
        <Tooltip :text="titles.get(id) ?? ''">
          <span class="mono">{{ id }}</span>
        </Tooltip>
        <button
          type="button"
          class="remove"
          :aria-label="`Odebrat ${id}`"
          :disabled="disabled"
          :data-test="`unpick-${id}`"
          @click="remove(id)"
        >
          <X :size="12" aria-hidden="true" />
        </button>
      </li>
    </ul>
    <SelectMenu
      v-bind="$attrs"
      model-value=""
      :options="free"
      :label="label"
      :disabled="disabled || !free.length"
      :placeholder="free.length ? 'Přidat…' : 'Není co přidat'"
      @update:model-value="add"
    />
  </div>
</template>

<style scoped>
.id-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.picked {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.picked li {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 2px 1px 8px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
}

.mono {
  font-family: var(--mono);
  font-size: 13px;
}

button.remove {
  display: inline-flex;
  padding: 2px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--dim);
  cursor: pointer;
}

button.remove:hover:not(:disabled) {
  color: var(--red);
}

button.remove:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>

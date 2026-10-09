<script setup lang="ts">
// The `auto_continue` switch of a module or step (`factory backlog auto-continue`); with
// `label="Auto-merge" test-prefix="merge"` the `auto_merge` one (`factory backlog auto-merge`).
import type { AutoMode } from '@/lib/backlog'
import Spinner from '@/components/ui/Spinner.vue'

withDefaults(
  defineProps<{
    mode: AutoMode
    effective: boolean
    busy: boolean
    disabled?: boolean
    /** The mode being saved (spinner in its button). */
    pending?: AutoMode | null
    /** Label and aria-label of the switch. */
    label?: string
    /** Prefix of the data-test attributes. */
    testPrefix?: string
    /** Hint shown next to the switch. */
    hint?: string
  }>(),
  { label: 'Auto-continue', testPrefix: 'auto', disabled: false, pending: null, hint: '' },
)
const emit = defineEmits<{ change: [mode: AutoMode] }>()

const OPTIONS: readonly { mode: AutoMode; label: string }[] = [
  { mode: 'inherit', label: 'Zděděno' },
  { mode: 'on', label: 'Zapnuto' },
  { mode: 'off', label: 'Vypnuto' },
]
</script>

<template>
  <div class="auto-toggle" :data-test="`${testPrefix}-toggle`">
    <span class="label">{{ label }}</span>
    <div class="segment" role="group" :aria-label="label">
      <button
        v-for="option in OPTIONS"
        :key="option.mode"
        type="button"
        :data-test="`${testPrefix}-${option.mode}`"
        :class="{ active: option.mode === mode }"
        :aria-pressed="option.mode === mode"
        :disabled="busy || disabled"
        :aria-busy="option.mode === pending || undefined"
        @click="option.mode !== mode && emit('change', option.mode)"
      >
        <Spinner v-if="option.mode === pending" />
        {{ option.label }}
      </button>
    </div>
    <span class="effective faint" :data-test="`${testPrefix}-effective`">
      efektivně: {{ effective ? 'zapnuto' : 'vypnuto' }}
    </span>
    <span v-if="hint" class="effective faint" :data-test="`${testPrefix}-hint`">{{ hint }}</span>
  </div>
</template>

<style scoped>
.auto-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
}

.label {
  color: var(--dim);
}

.segment {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: none;
  border-right: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

button:last-child {
  border-right: none;
}

button.active {
  background: rgba(90, 210, 221, 0.15);
  color: var(--cyan);
  font-weight: 600;
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}

.effective {
  font-size: 14px;
}
</style>

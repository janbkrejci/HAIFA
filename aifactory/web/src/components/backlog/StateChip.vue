<script setup lang="ts">
import { computed } from 'vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { STATE_LABELS, STATE_TOOLTIPS, blockedTooltip, type BoardState, type Unmet } from '@/lib/backlog'
import { useNames } from '@/lib/names'

// `count`: the chip shows a number of tasks in the state (`Hotovo 5`).
const props = defineProps<{ state: BoardState; blockedBy?: Unmet[]; count?: number }>()

const cls = computed(() => `state-${props.state.replace(/\s+/g, '-')}`)
const label = computed(() => {
  const name = STATE_LABELS[props.state] ?? props.state
  return props.count === undefined ? name : `${name} ${props.count}`
})
// Blokováno explains what blocks the task and why; Bez workflow why it cannot run.
const { names } = useNames()
const tip = computed(() =>
  props.state === 'blocked'
    ? blockedTooltip(props.blockedBy, names.value)
    : (STATE_TOOLTIPS[props.state] ?? ''),
)
</script>

<template>
  <Tooltip v-if="tip" :text="tip">
    <span class="chip" :class="cls" :data-state="state" tabindex="0" :data-test="state === 'blocked' ? 'blocked-chip' : 'state-tip-chip'">{{ label }}</span>
  </Tooltip>
  <span v-else class="chip" :class="cls" :data-state="state">{{ label }}</span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 14px;
  color: var(--dim);
  white-space: nowrap;
}

.state-todo {
  border-style: dashed;
}

.state-ready {
  color: var(--cyan);
  border-color: rgba(90, 210, 221, 0.45);
  background: rgba(90, 210, 221, 0.08);
}

.state-blocked {
  color: var(--amber);
  border-color: rgba(232, 182, 74, 0.45);
  background: rgba(232, 182, 74, 0.08);
}

.chip[tabindex] {
  cursor: help;
}

.state-running {
  color: var(--blue);
  border-color: rgba(108, 182, 255, 0.45);
  background: rgba(108, 182, 255, 0.09);
}

.state-in-review {
  color: var(--purple);
  border-color: rgba(200, 155, 255, 0.45);
  background: rgba(200, 155, 255, 0.08);
}

.state-done {
  color: var(--green);
  border-color: rgba(74, 222, 128, 0.45);
  background: rgba(74, 222, 128, 0.09);
}

.state-cancelled {
  color: var(--faint);
  text-decoration: line-through;
}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import {
  STATE_LABELS,
  STATE_TOOLTIPS,
  WAITS_FOR_HUMAN_LABEL,
  blockedTooltip,
  type BoardState,
  type Unmet,
} from '@/lib/backlog'
import { useNames } from '@/lib/names'
import { stateClass } from '@/lib/overview'

// `count`: the chip shows a number of tasks in the state (`Hotovo 5`).
// `waitsForHuman`: unmet dependencies that are a person's tasks; a blocked task then reads
// Čeká na člověka in the colour of Pro člověka.
const props = defineProps<{ state: BoardState; blockedBy?: Unmet[]; count?: number; waitsForHuman?: string[] }>()

const forHuman = computed(() => props.state === 'blocked' && !!props.waitsForHuman?.length)
// The state colours are shared with the overview task summary (style.css, `.state-chip`).
const cls = computed(() => ['state-chip', stateClass(forHuman.value ? 'human' : props.state)])
const label = computed(() => {
  const name = forHuman.value ? WAITS_FOR_HUMAN_LABEL : (STATE_LABELS[props.state] ?? props.state)
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
  font-size: 14px;
  white-space: nowrap;
}

.chip[tabindex] {
  cursor: help;
}
</style>

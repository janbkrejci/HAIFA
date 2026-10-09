<script setup lang="ts">
// Port of the sssf visualizer's StatChip; runtime is in seconds.
import { computed } from 'vue'
import { BookOpen, CircleDollarSign, Coins, PenLine, Timer } from 'lucide-vue-next'
import { fmtCost, fmtDuration, fmtTokens } from '@/lib/format'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{
  kind: 'cost' | 'tokens' | 'runtime' | 'read' | 'written'
  value: number | null | undefined
  /** Smaller pill for tight spots like event rows. */
  compact?: boolean
  /** No tooltip and not focusable: for use inside another control (a waterfall block). */
  plain?: boolean
}>()

const ICONS = {
  cost: CircleDollarSign,
  tokens: Coins,
  runtime: Timer,
  read: BookOpen,
  written: PenLine,
}

const TITLES = {
  cost: 'Náklady – dolary za všechny agenty běhu.',
  tokens: 'Tokeny (účtované) – vše odeslané a vygenerované, v každém tahu znovu.',
  runtime: 'Doba běhu.',
  read: 'Přečteno – tokeny, které vstoupily do kontextu poprvé (bez cache re-readů).',
  written: 'Zapsáno – tokeny, které modely vygenerovaly.',
}

const text = computed(() => {
  if (props.kind === 'cost') return fmtCost(props.value)
  if (props.kind === 'runtime') return fmtDuration(props.value)
  return fmtTokens(props.value)
})
</script>

<template>
  <span v-if="plain" class="stat" :class="{ compact }" :data-stat="kind">
    <component :is="ICONS[kind]" class="stat-icon" :size="compact ? 15 : 18" :stroke-width="2" />
    <span class="stat-value">{{ text }}</span>
  </span>
  <Tooltip v-else :text="TITLES[kind]">
    <span class="stat" :class="{ compact }" :data-stat="kind" tabindex="0">
      <component :is="ICONS[kind]" class="stat-icon" :size="compact ? 15 : 18" :stroke-width="2" />
      <span class="stat-value">{{ text }}</span>
    </span>
  </Tooltip>
</template>

<style scoped>
.stat {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: var(--panel-2);
  font-size: 15px;
  white-space: nowrap;
}

.stat.compact {
  gap: 5px;
  padding: 1px 8px;
  font-size: 14px;
}

.stat.compact .stat-value {
  color: var(--dim);
}

.stat-icon {
  color: var(--faint);
  flex: none;
}

.stat-value {
  color: var(--text);
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}
</style>

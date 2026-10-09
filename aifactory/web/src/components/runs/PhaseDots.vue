<script setup lang="ts">
// Port of the sssf visualizer's PhaseDots: one icon per phase, in seq order.
import { computed, type Component } from 'vue'
import { Check, Circle, Hourglass, LoaderCircle, X } from 'lucide-vue-next'
import { slotWaitLabel, type PhaseDot } from '@/lib/runs'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ phases: PhaseDot[] }>()

const ordered = computed(() => [...props.phases].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0)))

const ICONS: Record<string, Component> = {
  success: Check,
  running: LoaderCircle,
  queued: Circle,
  fail: X,
}

function waiting(p: PhaseDot): boolean {
  return p.status === 'running' && !!p.slot_wait
}

function dotLabel(p: PhaseDot): string {
  if (waiting(p) && p.slot_wait) return `${p.name} — ${slotWaitLabel(p.slot_wait)}`
  return `${p.name} — ${p.status}`
}
</script>

<template>
  <span class="dots">
    <Tooltip v-for="(p, i) in ordered" :key="`${p.seq}-${i}`" :text="dotLabel(p)">
      <span
        class="d"
        :class="waiting(p) ? 'waiting' : p.status"
        tabindex="0"
        :aria-label="dotLabel(p)"
        :data-slot-wait="waiting(p) ? p.slot_wait?.ahead : undefined"
      >
        <component
          :is="waiting(p) ? Hourglass : (ICONS[p.status ?? ''] ?? Circle)"
          :size="15"
          :stroke-width="2.5"
        />
      </span>
    </Tooltip>
    <span v-if="!ordered.length" class="faint">—</span>
  </span>
</template>

<style scoped>
.dots {
  display: inline-flex;
  gap: 4px;
}

.d {
  color: var(--faint);
}

.d.success {
  color: var(--green);
}

.d.fail {
  color: var(--red);
}

.d.waiting {
  color: var(--amber);
}

.d.running {
  color: var(--blue);
  animation: pulse 1.2s ease-in-out infinite;
}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, Circle, LoaderCircle, X } from 'lucide-vue-next'
import type { Phase } from '../lib/types'

const props = defineProps<{ phases: Phase[] }>()

const ordered = computed(() => props.phases.toSorted((a, b) => (a.seq ?? 0) - (b.seq ?? 0)))

const ICONS: Record<string, unknown> = {
  success: Check,
  running: LoaderCircle,
  queued: Circle,
  fail: X,
}
</script>

<template>
  <span class="dots">
    <span
      v-for="p in ordered"
      :key="p.phase_id"
      class="d"
      :class="p.status"
      :title="`${p.name} — ${p.status}`"
    >
      <component :is="ICONS[p.status ?? ''] ?? Circle" :size="16" :stroke-width="2.5" />
    </span>
    <span v-if="!ordered.length" class="faint">—</span>
  </span>
</template>

<style scoped>
.dots {
  display: inline-flex;
  gap: 5px;
  font-size: 16px;
  letter-spacing: 0;
}

.d.success {
  color: var(--green);
}

.d.fail {
  color: var(--red);
}

.d.running {
  color: var(--blue);
  animation: pulse 1.2s ease-in-out infinite;
}

.d.running :deep(svg) {
  animation: spin 1.1s linear infinite;
}

.d.queued {
  color: var(--faint);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

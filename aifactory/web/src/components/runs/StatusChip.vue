<script setup lang="ts">
// Port of the sssf visualizer's StatusChip: run states and phase statuses, in Czech.
import { computed, type Component } from 'vue'
import { Ban, Check, Circle, CircleSlash, Hourglass, LoaderCircle, Pause, X } from 'lucide-vue-next'

const props = defineProps<{ status: string | null }>()

const KINDS: Record<string, { cls: string; label: string; icon: Component }> = {
  running: { cls: 'running', label: 'běží', icon: LoaderCircle },
  succeeded: { cls: 'success', label: 'úspěch', icon: Check },
  success: { cls: 'success', label: 'úspěch', icon: Check },
  failed: { cls: 'fail', label: 'chyba', icon: X },
  fail: { cls: 'fail', label: 'chyba', icon: X },
  aborted: { cls: 'aborted', label: 'přerušeno', icon: CircleSlash },
  stopped: { cls: 'stopped', label: 'zastaveno', icon: Ban },
  // a running run that waits before its next phase (factory task pause), or will
  paused: { cls: 'paused', label: 'pozastaveno', icon: Pause },
  pausing: { cls: 'pausing', label: 'pozastavuje se', icon: Hourglass },
  queued: { cls: 'queued', label: 'čeká', icon: Circle },
}

const kind = computed(
  () => KINDS[props.status ?? ''] ?? { cls: 'queued', label: props.status ?? '—', icon: Circle },
)
</script>

<template>
  <span class="chip" :class="kind.cls" :data-status="status">
    <component :is="kind.icon" class="chip-icon" :size="16" :stroke-width="2.5" />
    {{ kind.label }}
  </span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 11px 2px 9px;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 15px;
  color: var(--dim);
  white-space: nowrap;
}

.chip-icon {
  flex: none;
}

.chip.success {
  color: var(--green);
  border-color: rgba(74, 222, 128, 0.45);
  background: rgba(74, 222, 128, 0.09);
}

.chip.fail {
  color: var(--red);
  border-color: rgba(255, 111, 103, 0.45);
  background: rgba(255, 111, 103, 0.09);
}

.chip.running {
  color: var(--blue);
  border-color: rgba(108, 182, 255, 0.45);
  background: rgba(108, 182, 255, 0.09);
}

.chip.running .chip-icon {
  animation: spin 1.1s linear infinite;
}

.chip.aborted,
.chip.stopped {
  color: var(--amber);
  border-color: rgba(232, 182, 74, 0.45);
  background: rgba(232, 182, 74, 0.08);
}

.chip.paused,
.chip.pausing {
  color: var(--cyan);
  border-color: rgba(103, 232, 249, 0.45);
  background: rgba(103, 232, 249, 0.08);
}

.chip.pausing {
  border-style: dashed;
}

.chip.queued {
  border-style: dashed;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

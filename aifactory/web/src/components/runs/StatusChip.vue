<script setup lang="ts">
import { t } from '@/lib/i18n'
// Port of the sssf visualizer's StatusChip: run states and phase statuses, in Czech.
import { computed, type Component } from 'vue'
import { Ban, Check, Circle, CircleSlash, Hourglass, LoaderCircle, Lock, Pause, X } from 'lucide-vue-next'

const props = defineProps<{ status: string | null }>()

const KINDS = computed<Record<string, { cls: string; label: string; icon: Component }>>(() => ({
  running: { cls: 'running', label: t('runs.bezi_169'), icon: LoaderCircle },
  succeeded: { cls: 'success', label: t('runs.uspech'), icon: Check },
  success: { cls: 'success', label: t('runs.uspech'), icon: Check },
  failed: { cls: 'fail', label: t('runs.chyba'), icon: X },
  fail: { cls: 'fail', label: t('runs.chyba'), icon: X },
  // a failed run that waits for its blocking tasks (failure kind blocked): not a failure
  blocked: { cls: 'blocked', label: t('runs.blokovany'), icon: Lock },
  aborted: { cls: 'aborted', label: t('runs.preruseno'), icon: CircleSlash },
  stopped: { cls: 'stopped', label: t('runs.zastaveno'), icon: Ban },
  // a running run that waits before its next phase (factory task pause), or will
  paused: { cls: 'paused', label: t('runs.pozastaveno'), icon: Pause },
  pausing: { cls: 'pausing', label: t('runs.pozastavuje_se'), icon: Hourglass },
  queued: { cls: 'queued', label: t('runs.ceka'), icon: Circle },
}))

const kind = computed(
  () => KINDS.value[props.status ?? ''] ?? { cls: 'queued', label: props.status ?? '—', icon: Circle },
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

.chip.blocked {
  color: var(--violet);
  border-color: rgba(148, 163, 255, 0.45);
  background: rgba(148, 163, 255, 0.09);
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

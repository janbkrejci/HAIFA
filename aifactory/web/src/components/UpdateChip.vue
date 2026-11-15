<script setup lang="ts">
import { t } from '@/lib/i18n'
import './ui/statusIconChip.css'
import { computed } from 'vue'
import { ArrowUpCircle, ClockCheck, Info, TriangleAlert } from 'lucide-vue-next'
import { useUpdates } from '@/lib/updates'
import Spinner from './ui/Spinner.vue'
import Tooltip from './ui/Tooltip.vue'

const updates = useUpdates()
const state = updates.state
const label = computed(() => ({
  checking: t('updates.checking'),
  current: t('updates.current'),
  available: t('updates.available'),
  waiting: t('updates.waiting'),
  error: t('updates.error'),
  installing: t('updates.installing'),
})[state.value.status])
const hint = computed(() => state.value.error_code ? t(`updates.${state.value.error_code}`) : (state.value.status === 'available'
  ? t('updates.installHint', { version: state.value.target_version ?? '' })
  : t('updates.retryHint')))
const description = computed(() => `${label.value} – ${hint.value}`)
</script>

<template>
  <span class="update-indicator">
    <Tooltip :text="description">
      <button type="button" class="status-icon-chip update-chip" :class="state.status" :aria-label="description" :disabled="state.status === 'checking' || state.status === 'installing'" data-test="update-chip" @click="updates.activate">
        <Spinner v-if="state.status === 'checking' || state.status === 'installing'" />
        <ClockCheck v-else-if="state.status === 'current'" :size="14" aria-hidden="true" />
        <ArrowUpCircle v-else-if="state.status === 'available'" :size="14" aria-hidden="true" />
        <TriangleAlert v-else :size="14" aria-hidden="true" />
      </button>
    </Tooltip>
    <details v-if="state.error" class="update-diagnostics" data-test="update-diagnostics">
      <summary :aria-label="t('dashboard.diagnostics')"><Info :size="14" aria-hidden="true" /></summary>
      <div class="diagnostics-panel"><strong>{{ t('dashboard.diagnostics') }}</strong><pre>{{ state.error }}</pre></div>
    </details>
  </span>
</template>

<style scoped>
.update-indicator { position: relative; display: inline-flex; align-items: center; gap: 4px; }
.update-diagnostics summary { cursor: pointer; display: flex; color: var(--amber); }
.diagnostics-panel { position: absolute; right: 0; top: 100%; z-index: var(--z-tooltip); width: min(320px, 80vw); padding: 10px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; }
.diagnostics-panel pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.update-chip:disabled { opacity: 1; cursor: progress; }
.checking, .installing { color: var(--blue); }
.current { color: var(--green); }
.available, .waiting, .error { color: var(--amber); }
</style>

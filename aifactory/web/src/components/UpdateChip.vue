<script setup lang="ts">
import { t } from '@/lib/i18n'
import './ui/statusIconChip.css'
import { computed } from 'vue'
import { ArrowUpCircle, ClockCheck, TriangleAlert } from 'lucide-vue-next'
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
const hint = computed(() => state.value.error || (state.value.status === 'available'
  ? t('updates.installHint', { version: state.value.target_version ?? '' })
  : t('updates.retryHint')))
const description = computed(() => `${label.value} – ${hint.value}`)
</script>

<template>
  <Tooltip :text="description">
    <button type="button" class="status-icon-chip update-chip" :class="state.status" :aria-label="description" :disabled="state.status === 'checking' || state.status === 'installing'" data-test="update-chip" @click="updates.activate">
      <Spinner v-if="state.status === 'checking' || state.status === 'installing'" />
      <ClockCheck v-else-if="state.status === 'current'" :size="14" aria-hidden="true" />
      <ArrowUpCircle v-else-if="state.status === 'available'" :size="14" aria-hidden="true" />
      <TriangleAlert v-else :size="14" aria-hidden="true" />
    </button>
  </Tooltip>
</template>

<style scoped>
.update-chip:disabled { opacity: 1; cursor: progress; }
.checking, .installing { color: var(--blue); }
.current { color: var(--green); }
.available, .waiting, .error { color: var(--amber); }
</style>

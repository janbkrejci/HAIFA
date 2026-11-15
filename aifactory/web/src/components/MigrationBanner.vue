<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/lib/i18n'
import { useUpdates } from '@/lib/updates'
import Spinner from './ui/Spinner.vue'

const updates = useUpdates({ migration: true })
const state = updates.state
const visible = computed(() => !state.value.current_version.startsWith('1.'))
const busy = computed(() => ['checking', 'installing'].includes(state.value.status))
</script>

<template>
  <aside v-if="visible" class="migration-banner" data-test="migration-banner" :aria-label="t('migration.title')">
    <strong>{{ t('migration.title') }}</strong>
    <button type="button" :disabled="busy" data-test="migration-action" @click="updates.install">
      <Spinner v-if="state.status === 'installing'" />
      {{ state.status === 'installing' ? t('migration.installing') : t('migration.action') }}
    </button>
    <span v-if="state.error_code" role="status">{{ t(`updates.${state.error_code}`) }}</span>
    <details v-if="state.error">
      <summary>{{ t('dashboard.diagnostics') }}</summary>
      <pre>{{ state.error }}</pre>
    </details>
  </aside>
</template>

<style scoped>
.migration-banner { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 28px; background: var(--panel-2); border-bottom: 1px solid var(--amber); }
button { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--amber); border-radius: 6px; background: var(--panel-2); color: var(--text); font: inherit; cursor: pointer; }
button:disabled { cursor: progress; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
